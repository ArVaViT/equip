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
 * through five states as the document scrolls:
 *
 *   scattered   loose pieces — the hero, «не отрывками»
 *   stacked     squared up, one on another      (first claim)
 *   fanned      a row: the shape of a course    (second claim)
 *   single      one sheet forward, the rest back (third claim)
 *   dispersed   opening outward as the page ends
 *
 * WHERE EACH POSE LANDS. They used to sit at fixed fractions of the
 * document — 0.22, 0.45, 0.68 — which was true only for one page height.
 * Lengthening the claims track (2026-09-23, «очень быстрая прокрутка»)
 * would have slid every pose off the caption it belongs to. So the claims
 * section marks its own stops with `data-backdrop-pose`, and the scene
 * reads their positions: pose N is fully formed exactly when the reader
 * rests on stop N. The first pose is the top of the page and the last is
 * its end, so only the middle three need marking. If the markers are
 * missing (phone layout, reduced motion) the poses spread evenly, which is
 * what the fractions were approximating anyway.
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

/** Deterministic pseudo-random in [0, 1) — the same scene on every load. */
function noise(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

type Pose = { x: number; y: number; z: number; rx: number; ry: number; rz: number }

/** The five poses of leaf `i`, in scroll order. */
function posesFor(i: number): Pose[] {
  const depth = -i * 0.36
  const centre = (LEAF_COUNT - 1) / 2
  const column = i - centre
  const spread = centre === 0 ? 0 : column / centre

  return [
    // scattered
    {
      x: spread * 7.5,
      y: (noise(i, 2) - 0.5) * 5.5,
      z: depth,
      rx: (noise(i, 3) - 0.5) * 1.1,
      ry: (noise(i, 4) - 0.5) * 1.3,
      rz: (noise(i, 5) - 0.5) * 0.9,
    },
    // stacked
    { x: 0, y: 0, z: depth, rx: 0, ry: 0, rz: 0 },
    // fanned into a row that runs off both edges
    {
      x: column * 2.1,
      y: (noise(i, 7) - 0.5) * 0.6,
      z: depth * 0.4,
      rx: 0,
      ry: -0.2,
      rz: (noise(i, 8) - 0.5) * 0.07,
    },
    // one forward, the rest pushed back
    i === LEAF_COUNT - 1
      ? { x: 0, y: 0, z: 3.2, rx: 0, ry: 0, rz: 0 }
      : {
          x: column * 0.8,
          y: (noise(i, 9) - 0.5) * 1.6,
          z: depth - 3,
          rx: 0,
          ry: -0.1,
          rz: (noise(i, 10) - 0.5) * 0.25,
        },
    // dispersed outward as the page runs out
    {
      x: spread * 13,
      y: (noise(i, 11) - 0.5) * 9,
      z: depth - 6,
      rx: (noise(i, 12) - 0.5) * 0.9,
      ry: (noise(i, 13) - 0.5) * 1.1,
      rz: (noise(i, 14) - 0.5) * 0.8,
    },
  ]
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
    const leafOpacity = (i: number) =>
      (0.022 + 0.1 * (i / LEAF_COUNT)) * (isDark() ? DARK_BOOST : 1)

    const readInk = () => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim()
      return new Color(raw ? `hsl(${raw})` : "#131211")
    }

    const scene = new Scene()
    const camera = new PerspectiveCamera(32, 1, 0.1, 100)
    camera.position.set(0, 0, 14)

    scene.add(new AmbientLight(0xffffff, 1.6))
    const key = new DirectionalLight(0xffffff, 2.2)
    key.position.set(4, 6, 8)
    scene.add(key)

    const group = new Group()
    scene.add(group)

    const geometry = new PlaneGeometry(4, 5.4)
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
        opacity: leafOpacity(i),
        roughness: 0.85,
        metalness: 0,
      })
      const mesh = new Mesh(geometry, material)
      group.add(mesh)
      return { mesh, material, poses: posesFor(i) }
    })

    // Follows the theme without a second palette to keep in sync.
    const themeWatcher = new MutationObserver(() => {
      const ink = readInk()
      leaves.forEach((leaf, i) => {
        leaf.material.color.copy(ink)
        leaf.material.opacity = leafOpacity(i)
      })
    })
    themeWatcher.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    })

    // Pose coordinate: 0 = first pose, 4 = last, fractional in between.
    let progress = 0
    let target = 0
    const lastPose = (leaves[0]?.poses.length ?? 1) - 1
    // Scroll offsets at which each pose is complete. Re-measured on resize
    // and whenever the document changes height (the shelf arriving from the
    // network moves everything below the claims).
    let stops: number[] = []
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
      const travel = Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
      const marked = [...document.querySelectorAll<HTMLElement>("[data-backdrop-pose]")]
        .map((el) => el.getBoundingClientRect().top + window.scrollY)
        .sort((a, b) => a - b)
      const middle =
        marked.length === lastPose - 1
          ? marked
          : Array.from({ length: lastPose - 1 }, (_, k) => (travel * (k + 1)) / lastPose)
      stops = [0, ...middle, Math.max(travel, (middle[middle.length - 1] ?? 0) + 1)]
    }

    const readScroll = () => {
      const y = window.scrollY
      let pose = lastPose
      for (let k = 0; k < stops.length - 1; k++) {
        const from = stops[k] ?? 0
        const to = stops[k + 1] ?? from + 1
        if (y < to) {
          pose = k + Math.max(0, (y - from) / Math.max(1, to - from))
          break
        }
      }
      target = Math.min(lastPose, Math.max(0, pose))
    }

    const onPointerMove = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth) * 2 - 1
      pointerY = (event.clientY / window.innerHeight) * 2 - 1
    }

    const applyPose = () => {
      const index = Math.min(lastPose - 1, Math.floor(progress))
      const t = ease(progress - index)

      for (const leaf of leaves) {
        const from = leaf.poses[index]
        const to = leaf.poses[index + 1]
        if (!from || !to) continue
        leaf.mesh.position.set(
          lerp(from.x, to.x, t),
          lerp(from.y, to.y, t),
          lerp(from.z, to.z, t),
        )
        leaf.mesh.rotation.set(
          lerp(from.rx, to.rx, t),
          lerp(from.ry, to.ry, t),
          lerp(from.rz, to.rz, t),
        )
      }
    }

    const render = () => {
      applyPose()
      group.rotation.x = tiltX
      group.rotation.y = tiltY
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
