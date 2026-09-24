import { useEffect, useRef } from "react"
import {
  AmbientLight,
  Color,
  DirectionalLight,
  Group,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  WebGLRenderer,
} from "three"

/**
 * One scene behind the whole page, from the first screen to the last.
 *
 * It used to be two: a scene pinned to the hero and a second one pinned to
 * the claims, with nothing behind the shelf, the close or the film. Which
 * is exactly what Vadym noticed — «фоновый моушн прикольно в начале почему
 * он дальше не продолжается до конца страницы?». Two scenes also meant two
 * WebGL contexts and one idea stated twice.
 *
 * Now a single fixed canvas sits behind everything and the leaves move
 * through a sequence of poses as the document scrolls — one per scene:
 *
 *   scattered   loose pieces — the hero, «не отрывками»
 *   stacked     squared up, one on another       (first claim)
 *   fanned      a row: the shape of a course     (second claim)
 *   single      one sheet forward, the rest back (third claim)
 *   frame       every piece squared into one rectangle around the tour
 *   row         laid out in order, one per course, riding the shelf
 *   gather      collected into one neat stack    (the close)
 *   frame       squared round the film, and held to the end
 *
 * THE SCENE LEADS THE EYE. Until 2026-09-23 the leaves stopped having
 * anything to do with the page after the claims: the tour, the shelf and
 * the film sat on top of them as if on an empty table. Vadym: «я думал ты
 * будешь вести так анимацию, чтоб она выделяла блок … все фрагменты
 * собираются в прямоугольник и потом раскладываются по порядку». So the
 * last four poses are not coordinates but *elements*: `frame` and `row`
 * read the live on-screen rectangle of what they surround (the video, the
 * row of covers) every frame and convert it into world units, so the
 * pieces close in on the video as it arrives and slide along with the
 * shelf as it travels. The argument of the page — fragments put in order —
 * is made by the scene around the product, not only above it.
 *
 * WHERE EACH POSE LANDS. Each scene marks itself with
 * `data-backdrop-pose="<kind>"`; the pose is fully formed exactly when the
 * reader rests on that scene's stop (the same stop `pageScroll.ts` uses).
 * The DOM poses find what to wrap through `data-backdrop-target` inside the
 * scene. A scene that is not rendered — the shelf with an empty catalogue —
 * simply drops out of the sequence.
 *
 * The states are the argument of the page told without words, and because
 * the canvas is `fixed` it is continuous: nothing restarts at a section
 * boundary, and the reader never scrolls past the movement into a still
 * page.
 *
 * WHY `fixed` AND NOT ONE STICKY PER SECTION. A sticky canvas is released
 * at the end of its own track, which is what produced the dead stretches.
 * Fixed has no track to leave. It costs one composited layer, which is what
 * the browser was already doing for each sticky canvas anyway.
 *
 * COST AND ITS FENCES. `three` is ~126KB gzipped, lazily imported from the
 * landing page alone; not mounted at all under `prefers-reduced-motion` or
 * where WebGL is missing; and the loop stops whenever the document is
 * hidden, so a backgrounded tab is not quietly turning a laptop fan.
 */

const LEAF_COUNT = 16
const LEAF_W = 4
const LEAF_H = 5.4
const CAMERA_FOV = 32
const CAMERA_Z = 14

/** Deterministic pseudo-random in [0, 1) — the same scene on every load. */
function noise(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

type Pose = {
  x: number
  y: number
  z: number
  rx: number
  ry: number
  rz: number
  sx: number
  sy: number
  /** Multiplier on the leaf's own opacity. */
  o: number
}

type Kind = "scattered" | "stacked" | "fanned" | "single" | "gather" | "frame" | "row"

const STATIC_KINDS = ["scattered", "stacked", "fanned", "single", "gather"] as const
type StaticKind = (typeof STATIC_KINDS)[number]

const isStatic = (kind: Kind): kind is StaticKind =>
  (STATIC_KINDS as readonly string[]).includes(kind)

/** The coordinate poses of leaf `i` — the ones that do not wrap an element. */
function staticPose(kind: StaticKind, i: number): Pose {
  const depth = -i * 0.36
  const centre = (LEAF_COUNT - 1) / 2
  const column = i - centre
  const spread = centre === 0 ? 0 : column / centre
  const flat = { rx: 0, ry: 0, rz: 0, sx: 1, sy: 1, o: 1 }

  switch (kind) {
    case "scattered":
      return {
        x: spread * 7.5,
        y: (noise(i, 2) - 0.5) * 5.5,
        z: depth,
        rx: (noise(i, 3) - 0.5) * 1.1,
        ry: (noise(i, 4) - 0.5) * 1.3,
        rz: (noise(i, 5) - 0.5) * 0.9,
        sx: 1,
        sy: 1,
        o: 1,
      }
    case "stacked":
      return { ...flat, x: 0, y: 0, z: depth }
    case "fanned":
      return {
        ...flat,
        x: column * 2.1,
        y: (noise(i, 7) - 0.5) * 0.6,
        z: depth * 0.4,
        ry: -0.2,
        rz: (noise(i, 8) - 0.5) * 0.07,
      }
    case "single":
      return i === LEAF_COUNT - 1
        ? { ...flat, x: 0, y: 0, z: 3.2 }
        : {
            ...flat,
            x: column * 0.8,
            y: (noise(i, 9) - 0.5) * 1.6,
            z: depth - 3,
            ry: -0.1,
            rz: (noise(i, 10) - 0.5) * 0.25,
          }
    case "gather":
      // One neat deck behind the question, each sheet a hair off square —
      // the pieces collected, about to be handed over.
      // Light: all sixteen overlap here, directly behind body text, and
      // at full strength the deck was a grey slab the subline sank into.
      return {
        ...flat,
        x: 0,
        y: 0,
        z: depth * 0.25 - 2,
        rz: column * 0.028,
        sx: 1.35,
        sy: 0.95,
        o: 0.22,
      }
  }
}

/** World units per CSS pixel at depth `z`, for this camera. */
function worldPerPixel(z: number): number {
  const distance = CAMERA_Z - z
  return (2 * Math.tan(((CAMERA_FOV / 2) * Math.PI) / 180) * distance) / window.innerHeight
}

/** A screen rectangle, expressed as a pose for a plane at depth `z`. */
function poseForRect(
  left: number,
  top: number,
  width: number,
  height: number,
  z: number,
  o: number,
): Pose {
  const wpp = worldPerPixel(z)
  return {
    x: (left + width / 2 - window.innerWidth / 2) * wpp,
    y: (window.innerHeight / 2 - (top + height / 2)) * wpp,
    z,
    rx: 0,
    ry: 0,
    rz: 0,
    sx: (width * wpp) / LEAF_W,
    sy: (height * wpp) / LEAF_H,
    o,
  }
}

/**
 * `frame`: all sixteen squared into one rectangle around the element, each
 * a few pixels larger than the one in front — so the edges step outward
 * like the edges of a stack of paper, and the rectangle reads as made of
 * the same pieces that were scattered over the hero. Kept close (under
 * 70px) and light: sixteen translucent layers compound, and at full
 * strength the first version read as a dark tunnel round the video.
 */
function framePose(rect: DOMRect, i: number): Pose {
  const pad = 4 + i * 4
  return poseForRect(
    rect.left - pad,
    rect.top - pad,
    rect.width + pad * 2,
    rect.height + pad * 2,
    -0.4 - i * 0.02,
    0.32,
  )
}

/**
 * `row`: the pieces dealt out in order, a few to each cover, as the pages
 * behind it — every course becomes a small stack, offset down and to the
 * right like a book seen from its corner. Read from the live row, so the
 * stacks travel sideways with the covers.
 *
 * Every leaf goes to a real course. A first version laid one sheet per
 * *slot* and ran the row past both ends of the catalogue: grey panels
 * behind each card (the white box the cards had just lost) and empty ones
 * after the last course — placeholders, which this page does not have.
 */
function rowPose(row: HTMLElement, i: number): Pose {
  const count = row.children.length
  if (count === 0) return staticPose("stacked", i)
  const course = row.children[i % count]
  const layer = Math.floor(i / count)
  // The cover, not the whole card: the title underneath stays on the page.
  const cover = course?.firstElementChild?.firstElementChild?.getBoundingClientRect()
  if (!cover) return staticPose("stacked", i)
  const offset = 7 + layer * 7
  return poseForRect(
    cover.left + offset,
    cover.top + offset,
    cover.width,
    cover.height,
    -0.4 - layer * 0.02,
    0.55,
  )
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/** Smoothstep — takes the corner off each handover between states. */
const ease = (t: number) => {
  const c = Math.min(1, Math.max(0, t))
  return c * c * (3 - 2 * c)
}

export default function LandingBackdrop({ className }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    // Ask first, and ask on a canvas we throw away.
    //
    // The try/catch below is enough to keep the page working without WebGL
    // — it always was. What it cannot do is keep three.js quiet: the
    // renderer's constructor writes three `console.error` lines before it
    // throws, and Datadog RUM records a console error as an error. One
    // visitor on a machine with no GPU therefore filed five errors from
    // the landing page on 2026-09-22 ("GpuChannelHost creation failed"),
    // and the RUM monitor fires at ten in ten minutes: two such visitors
    // in the same ten minutes raise an alert about a page that is working
    // exactly as designed.
    //
    // A probe context on a detached canvas answers the same question
    // silently. It is released immediately; the renderer below makes its
    // own.
    const probe = document.createElement("canvas")
    const supported = Boolean(
      probe.getContext("webgl2") ?? probe.getContext("webgl"),
    )
    probe.width = probe.height = 0
    if (!supported) return

    let renderer: WebGLRenderer
    try {
      renderer = new WebGLRenderer({ alpha: true, antialias: true })
    } catch {
      // Still guarded: a context can be refused between the probe and here
      // (a second tab exhausting the browser's context budget is the
      // ordinary way). Nothing to show, nothing broken.
      return
    }

    // Light ink on a dark page reads fainter than dark ink on a light one
    // at the same alpha — measured on 2026-09-23, the dark scene was all but
    // invisible at the opacity that looked right in light. One factor for
    // the dark theme rather than a second palette.
    const DARK_BOOST = 1.9
    const isDark = () => document.documentElement.classList.contains("dark")
    const baseOpacity = (i: number) =>
      (0.022 + 0.1 * (i / LEAF_COUNT)) * (isDark() ? DARK_BOOST : 1)

    const readInk = () => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim()
      return new Color(raw ? `hsl(${raw})` : "#131211")
    }

    const scene = new Scene()
    const camera = new PerspectiveCamera(CAMERA_FOV, 1, 0.1, 100)
    camera.position.set(0, 0, CAMERA_Z)

    scene.add(new AmbientLight(0xffffff, 1.6))
    const key = new DirectionalLight(0xffffff, 2.2)
    key.position.set(4, 6, 8)
    scene.add(key)

    const group = new Group()
    scene.add(group)

    const geometry = new PlaneGeometry(LEAF_W, LEAF_H)
    const leaves = Array.from({ length: LEAF_COUNT }, (_, i) => {
      const material = new MeshStandardMaterial({
        color: readInk(),
        transparent: true,
        // Faint, and fainter toward the back. Translucent planes accumulate:
        // what is subtle alone goes solid where six of them cross.
        //
        // Raised by about 40% on 2026-09-23 — «анимацию на фоне сделай
        // чуточку менее прозрачной, что в светлой что в тёмной теме». Both
        // themes share this line because the colour is `--ink`, which is
        // already the right contrast direction in each; the ceiling is set
        // by the stacked pose, where all sixteen overlap behind a caption.
        opacity: baseOpacity(i),
        roughness: 0.85,
        metalness: 0,
      })
      const mesh = new Mesh(geometry, material)
      group.add(mesh)
      return { mesh, material }
    })

    // Follows the theme without a second palette to keep in sync.
    const themeWatcher = new MutationObserver(() => {
      const ink = readInk()
      for (const leaf of leaves) leaf.material.color.copy(ink)
      // Opacity is re-applied every frame from `baseOpacity`, which reads
      // the theme itself.
    })
    themeWatcher.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    })

    // The sequence of scenes, in scroll order, and the scroll offset at
    // which each one's pose is complete. Re-measured on resize and whenever
    // the document changes height (the shelf arriving from the network
    // moves everything below the claims).
    type Step = { kind: Kind; stop: number; target: HTMLElement | null }
    let steps: Step[] = [{ kind: "scattered", stop: 0, target: null }]
    // Pose coordinate: 0 = first step, fractional in between.
    let progress = 0
    let target = 0
    let pointerX = 0
    let pointerY = 0
    let tiltX = 0
    let tiltY = 0
    let frame = 0

    const resize = () => {
      const { innerWidth, innerHeight } = window
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.setSize(innerWidth, innerHeight, false)
      camera.aspect = innerWidth / innerHeight
      camera.updateProjectionMatrix()
    }

    const measureStops = () => {
      const vh = window.innerHeight
      const limit = Math.max(0, document.documentElement.scrollHeight - vh)
      const marked = [...document.querySelectorAll<HTMLElement>("[data-backdrop-pose]")]
        .map((el): Step => {
          const rect = el.getBoundingClientRect()
          const top = rect.top + window.scrollY
          const stop = el.dataset.sceneStop === "center" ? top + rect.height / 2 - vh / 2 : top
          return {
            kind: (el.dataset.backdropPose ?? "stacked") as Kind,
            stop: Math.min(limit, Math.max(1, stop)),
            target: el.querySelector<HTMLElement>("[data-backdrop-target]"),
          }
        })
        .filter((step) => isStatic(step.kind) || step.target !== null)
        .sort((a, b) => a.stop - b.stop)
      steps = [{ kind: "scattered", stop: 0, target: null }, ...marked]
    }

    const readScroll = () => {
      const y = window.scrollY
      const last = steps.length - 1
      let pose = last
      for (let k = 0; k < last; k++) {
        const from = steps[k]?.stop ?? 0
        const to = steps[k + 1]?.stop ?? from + 1
        if (y < to) {
          pose = k + Math.max(0, (y - from) / Math.max(1, to - from))
          break
        }
      }
      target = Math.min(last, Math.max(0, pose))
    }

    const onPointerMove = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth) * 2 - 1
      pointerY = (event.clientY / window.innerHeight) * 2 - 1
    }

    // Poses of one step for every leaf. DOM steps read their element's
    // rectangle once per frame, not once per leaf.
    const posesOf = (step: Step): Pose[] => {
      if (isStatic(step.kind)) {
        const kind = step.kind
        return leaves.map((_, i) => staticPose(kind, i))
      }
      const element = step.target
      if (!element) return leaves.map((_, i) => staticPose("stacked", i))
      if (step.kind === "row") return leaves.map((_, i) => rowPose(element, i))
      const rect = element.getBoundingClientRect()
      return leaves.map((_, i) => framePose(rect, i))
    }

    // How much of the current blend is wrapped round an element. The
    // pointer tilt is scaled down by it: a frame tilted by the cursor would
    // no longer sit square around the thing it frames.
    let anchored = 0

    const applyPose = () => {
      const last = steps.length - 1
      if (last < 1) return
      const index = Math.min(last - 1, Math.floor(progress))
      const t = ease(progress - index)
      const fromStep = steps[index]
      const toStep = steps[index + 1]
      if (!fromStep || !toStep) return
      const from = posesOf(fromStep)
      const to = posesOf(toStep)
      anchored =
        (isStatic(fromStep.kind) ? 0 : 1 - t) + (isStatic(toStep.kind) ? 0 : t)

      leaves.forEach((leaf, i) => {
        const a = from[i]
        const b = to[i]
        if (!a || !b) return
        leaf.mesh.position.set(lerp(a.x, b.x, t), lerp(a.y, b.y, t), lerp(a.z, b.z, t))
        leaf.mesh.rotation.set(lerp(a.rx, b.rx, t), lerp(a.ry, b.ry, t), lerp(a.rz, b.rz, t))
        leaf.mesh.scale.set(lerp(a.sx, b.sx, t), lerp(a.sy, b.sy, t), 1)
        leaf.material.opacity = baseOpacity(i) * lerp(a.o, b.o, t)
      })
    }

    const render = () => {
      applyPose()
      group.rotation.x = tiltX * (1 - anchored)
      group.rotation.y = tiltY * (1 - anchored)
      renderer.render(scene, camera)
    }

    const tick = () => {
      frame = requestAnimationFrame(tick)
      progress += (target - progress) * 0.07
      tiltX += (pointerY * 0.1 - tiltX) * 0.05
      tiltY += (pointerX * 0.2 - tiltY) * 0.05
      render()
    }

    const onVisibility = () => {
      cancelAnimationFrame(frame)
      if (!document.hidden) frame = requestAnimationFrame(tick)
    }

    host.appendChild(renderer.domElement)
    renderer.domElement.style.width = "100%"
    renderer.domElement.style.height = "100%"
    renderer.domElement.style.display = "block"
    resize()
    measureStops()
    readScroll()
    progress = target
    // One frame synchronously: rAF does not run in a background tab, and
    // this also removes the flash of empty canvas before the first frame.
    render()
    const onResize = () => {
      resize()
      measureStops()
      readScroll()
    }
    const layoutWatcher = new ResizeObserver(() => {
      measureStops()
      readScroll()
    })
    layoutWatcher.observe(document.body)
    window.addEventListener("resize", onResize)
    window.addEventListener("scroll", readScroll, { passive: true })
    window.addEventListener("pointermove", onPointerMove, { passive: true })
    document.addEventListener("visibilitychange", onVisibility)
    frame = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frame)
      themeWatcher.disconnect()
      layoutWatcher.disconnect()
      window.removeEventListener("resize", onResize)
      window.removeEventListener("scroll", readScroll)
      window.removeEventListener("pointermove", onPointerMove)
      document.removeEventListener("visibilitychange", onVisibility)
      geometry.dispose()
      for (const leaf of leaves) leaf.material.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  return <div ref={hostRef} className={className} aria-hidden />
}
