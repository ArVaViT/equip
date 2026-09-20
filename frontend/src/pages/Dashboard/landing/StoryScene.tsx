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
 * The part of the page below the hero, told in one continuous движение.
 *
 * The hero worked («первый кадр сочно реально») and what followed did not
 * («а дальше слабенько»): three paragraphs stacked under it, each fading in
 * once and then sitting still. Prose cannot follow a scene that moves.
 *
 * So this section does not stop moving. One sticky canvas is held for three
 * screens of scrolling while the same stack of leaves passes through three
 * states, and the words are captions to it rather than the other way round:
 *
 *   0.00 → 0.33   **stack**    — ordered, square, one on top of another.
 *   0.33 → 0.66   **spread**   — the stack fans into a row: modules beside
 *                                each other, the shape of a course.
 *   0.66 → 1.00   **single**   — one leaf comes forward and the rest recede:
 *                                the lesson you are actually reading.
 *
 * It is the hero's own scene continued, deliberately. A second unrelated
 * visual idea here would read as two pages glued together.
 *
 * COST. Shares the `three` chunk the hero already paid for — this module
 * adds no new dependency. A second WebGL context is cheap next to the first
 * one's download, and both stop rendering the moment they leave the
 * viewport. Not mounted at all under `prefers-reduced-motion`, and silently
 * absent where WebGL is missing; the captions stand on their own in both
 * cases, which is why they are real DOM text and not drawn into the canvas.
 */

// Nine, not fourteen. At fourteen the fanned row overlapped itself into
// a flat grey wall — the individual leaves stopped being visible as
// leaves, which is the one thing the middle state has to show.
const LEAF_COUNT = 9

/** Deterministic pseudo-random in [0, 1) — the same scene on every load. */
function noise(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

type Pose = { x: number; y: number; z: number; rx: number; ry: number; rz: number }

/** Where leaf `i` sits in each of the three states. */
function posesFor(i: number): [Pose, Pose, Pose] {
  const depth = -i * 0.34
  const stack: Pose = { x: 0, y: 0, z: depth, rx: 0, ry: 0, rz: 0 }

  // Fanned into a row. The spread is wider than the viewport on purpose:
  // the row should run off both edges, so it reads as part of something
  // longer rather than as fourteen objects arranged for the camera.
  const column = i - (LEAF_COUNT - 1) / 2
  const spread: Pose = {
    x: column * 2.35,
    y: (noise(i, 7) - 0.5) * 0.5,
    z: depth * 0.35,
    rx: 0,
    ry: -0.22,
    rz: (noise(i, 8) - 0.5) * 0.06,
  }

  // One leaf forward, the rest pushed back and out of the way.
  const isHero = i === LEAF_COUNT - 1
  const single: Pose = isHero
    ? { x: 0, y: 0, z: 3.4, rx: 0, ry: 0, rz: 0 }
    : {
        x: column * 0.7,
        y: (noise(i, 9) - 0.5) * 1.4,
        z: depth - 3,
        rx: 0,
        ry: -0.1,
        rz: (noise(i, 10) - 0.5) * 0.25,
      }

  return [stack, spread, single]
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function blend(from: Pose, to: Pose, t: number): Pose {
  return {
    x: lerp(from.x, to.x, t),
    y: lerp(from.y, to.y, t),
    z: lerp(from.z, to.z, t),
    rx: lerp(from.rx, to.rx, t),
    ry: lerp(from.ry, to.ry, t),
    rz: lerp(from.rz, to.rz, t),
  }
}

/** Smoothstep — removes the corner where one state hands over to the next. */
function ease(t: number): number {
  const c = Math.min(1, Math.max(0, t))
  return c * c * (3 - 2 * c)
}

export default function StoryScene({ className }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    let renderer: WebGLRenderer
    try {
      renderer = new WebGLRenderer({ alpha: true, antialias: true })
    } catch {
      return
    }

    const readInk = () => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim()
      return new Color(raw ? `hsl(${raw})` : "#131211")
    }

    const scene = new Scene()
    const camera = new PerspectiveCamera(30, 1, 0.1, 100)
    camera.position.set(0, 0, 13)

    scene.add(new AmbientLight(0xffffff, 1.7))
    const key = new DirectionalLight(0xffffff, 2.1)
    key.position.set(3, 5, 8)
    scene.add(key)

    const group = new Group()
    scene.add(group)

    const geometry = new PlaneGeometry(3.4, 4.6)
    const ink = readInk()
    const leaves = Array.from({ length: LEAF_COUNT }, (_, i) => {
      const material = new MeshStandardMaterial({
        color: ink,
        transparent: true,
        // Very faint, and fainter still toward the back. Overlapping
        // translucent planes accumulate: what looks subtle alone becomes
        // solid where six of them cross.
        opacity: 0.02 + 0.055 * (i / LEAF_COUNT),
        roughness: 0.85,
        metalness: 0,
      })
      const mesh = new Mesh(geometry, material)
      group.add(mesh)
      return { mesh, material, poses: posesFor(i) }
    })

    // `progress` follows the scroll with a lag, so a flick of the wheel
    // becomes a glide rather than a jump.
    let progress = 0
    let targetProgress = 0
    let pointerX = 0
    let pointerY = 0
    let tiltX = 0
    let tiltY = 0
    let visible = true
    let frame = 0

    const resize = () => {
      const { clientWidth, clientHeight } = host
      if (!clientWidth || !clientHeight) return
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.setSize(clientWidth, clientHeight, false)
      camera.aspect = clientWidth / clientHeight
      camera.updateProjectionMatrix()
    }

    // The scrolled fraction of the *track* — the tall parent the canvas is
    // stuck inside — not of the window. That is what makes the three states
    // line up with the three captions regardless of viewport height.
    const readProgress = () => {
      const track = host.parentElement?.parentElement
      if (!track) return
      const rect = track.getBoundingClientRect()
      const travel = rect.height - window.innerHeight
      if (travel <= 0) return
      targetProgress = Math.min(1, Math.max(0, -rect.top / travel))
    }

    const onPointerMove = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth) * 2 - 1
      pointerY = (event.clientY / window.innerHeight) * 2 - 1
    }

    const applyPose = () => {
      // Two segments: [stack → spread] then [spread → single].
      const scaled = progress * 2
      const index = scaled < 1 ? 0 : 1
      const t = ease(scaled - index)

      for (const leaf of leaves) {
        // Destructured rather than indexed: the tuple is three poses, and
        // `noUncheckedIndexedAccess` is right that `poses[index + 1]` proves
        // nothing on its own.
        const [stack, spread, single] = leaf.poses
        const pose = index === 0 ? blend(stack, spread, t) : blend(spread, single, t)
        leaf.mesh.position.set(pose.x, pose.y, pose.z)
        leaf.mesh.rotation.set(pose.rx, pose.ry, pose.rz)
      }
    }

    const tick = () => {
      frame = requestAnimationFrame(tick)
      if (!visible) return

      progress += (targetProgress - progress) * 0.07
      tiltX += (pointerY * 0.1 - tiltX) * 0.05
      tiltY += (pointerX * 0.18 - tiltY) * 0.05

      applyPose()
      group.rotation.x = tiltX
      group.rotation.y = tiltY
      renderer.render(scene, camera)
    }

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true
    })

    host.appendChild(renderer.domElement)
    renderer.domElement.style.width = "100%"
    renderer.domElement.style.height = "100%"
    renderer.domElement.style.display = "block"
    resize()
    readProgress()
    progress = targetProgress
    applyPose()
    // One frame synchronously: `requestAnimationFrame` does not run in a
    // background tab, and this also removes the flash of empty canvas
    // between mount and the first animation frame.
    renderer.render(scene, camera)
    observer.observe(host)
    window.addEventListener("resize", resize)
    window.addEventListener("scroll", readProgress, { passive: true })
    window.addEventListener("pointermove", onPointerMove, { passive: true })
    frame = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener("resize", resize)
      window.removeEventListener("scroll", readProgress)
      window.removeEventListener("pointermove", onPointerMove)
      geometry.dispose()
      for (const leaf of leaves) leaf.material.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  return <div ref={hostRef} className={className} aria-hidden />
}
