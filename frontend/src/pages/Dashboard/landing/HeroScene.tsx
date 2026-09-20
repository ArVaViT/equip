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
 * The hero's moving part: scattered leaves that square up into a stack.
 *
 * The headline argues «системно, а не отрывками», and this is that sentence
 * as geometry rather than as a second sentence. At rest the planes hang at
 * loose angles — fragments. As the page scrolls they rotate flat and draw
 * together into an ordered stack, and the cursor tilts the whole group a few
 * degrees, which is what makes it read as an object in a room instead of a
 * picture of one.
 *
 * WHY THE PLAIN `three` API AND NOT react-three-fiber. Fiber earns its
 * ~15KB when a scene is built from components that mount, update and unmount
 * with React state. This scene is one group of meshes created once and
 * driven by two numbers. Reconciling it through React would add a dependency
 * and a render loop to skip work that a `useRef` already does.
 *
 * COST, HONESTLY. `three` is about 150KB gzipped — larger than the entire
 * app shell. It is why this module is only ever reached through `lazy()`
 * from the landing page: a student opening a lesson never downloads it. The
 * bundle sentinel has a matching budget entry; see
 * `scripts/check-bundle-size.mjs`.
 *
 * WHEN IT DOES NOT RUN AT ALL:
 *
 * - `prefers-reduced-motion` — the caller does not mount it.
 * - No WebGL context (old phone, disabled in the browser, a headless test):
 *   the constructor throws, we swallow it and leave the canvas blank. The
 *   hero reads perfectly without this; the scene is the flourish, never the
 *   content.
 * - Off screen — the loop stops. A landing page whose first screen keeps a
 *   GPU busy while the reader is three sections down is a battery bug.
 */

const LEAF_COUNT = 18

/** Deterministic pseudo-random in [0, 1) — same scene on every load. */
function noise(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

export default function HeroScene({ className }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    let renderer: WebGLRenderer
    try {
      renderer = new WebGLRenderer({ alpha: true, antialias: true })
    } catch {
      // No WebGL. Nothing to clean up, nothing to show, nothing broken.
      return
    }

    // The scene borrows the page's own ink, so it follows the light/dark
    // switch without a second palette to keep in sync.
    const readInk = () => {
      const styles = getComputedStyle(document.documentElement)
      const raw = styles.getPropertyValue("--ink").trim()
      // Tokens are stored as raw HSL channels ("30 6% 7%"), which `Color`
      // does not parse; wrapping restores something CSS-shaped.
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

    const geometry = new PlaneGeometry(4.2, 5.6)
    const ink = readInk()
    const leaves = Array.from({ length: LEAF_COUNT }, (_, i) => {
      const material = new MeshStandardMaterial({
        color: ink,
        transparent: true,
        // Faint on purpose, and much fainter than the first attempt. At
        // 0.05-0.55 the leaves read as a stack of grey cards thrown over
        // the headline — busy, and competing with the words for a reader
        // who came for the words. The scene is a texture behind the claim,
        // not an illustration in front of it. Farther leaves are fainter
        // still: depth without a fog pass.
        opacity: 0.015 + 0.075 * (i / LEAF_COUNT),
        roughness: 0.85,
        metalness: 0,
      })
      const mesh = new Mesh(geometry, material)
      // Scattered pose — where a leaf sits before the page is scrolled.
      const scattered = {
        x: (noise(i, 1) - 0.5) * 7,
        y: (noise(i, 2) - 0.5) * 5,
        z: -i * 0.42,
        rx: (noise(i, 3) - 0.5) * 1.1,
        ry: (noise(i, 4) - 0.5) * 1.3,
        rz: (noise(i, 5) - 0.5) * 0.9,
      }
      // Ordered pose — the stack they settle into.
      const ordered = { x: 0, y: 0, z: -i * 0.42, rx: 0, ry: 0, rz: 0 }
      group.add(mesh)
      return { mesh, material, scattered, ordered }
    })

    let progress = 0 // 0 = scattered, 1 = stacked
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

    const onScroll = () => {
      // Fully stacked by the time the hero has scrolled one screen.
      targetProgress = Math.min(1, window.scrollY / Math.max(window.innerHeight, 1))
    }

    const onPointerMove = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth) * 2 - 1
      pointerY = (event.clientY / window.innerHeight) * 2 - 1
    }

    const tick = () => {
      frame = requestAnimationFrame(tick)
      if (!visible) return

      // Critically damped enough to feel weighty, never springy — the same
      // character as EDITORIAL_EASE elsewhere on the page.
      progress += (targetProgress - progress) * 0.06
      tiltX += (pointerY * 0.12 - tiltX) * 0.05
      tiltY += (pointerX * 0.22 - tiltY) * 0.05

      for (const leaf of leaves) {
        const { mesh, scattered: s, ordered: o } = leaf
        mesh.position.set(
          s.x + (o.x - s.x) * progress,
          s.y + (o.y - s.y) * progress,
          s.z,
        )
        mesh.rotation.set(
          s.rx + (o.rx - s.rx) * progress,
          s.ry + (o.ry - s.ry) * progress,
          s.rz + (o.rz - s.rz) * progress,
        )
      }

      group.rotation.x = tiltX
      group.rotation.y = tiltY
      renderer.render(scene, camera)
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry?.isIntersecting ?? true
      },
      { threshold: 0 },
    )

    host.appendChild(renderer.domElement)
    renderer.domElement.style.width = "100%"
    renderer.domElement.style.height = "100%"
    renderer.domElement.style.display = "block"
    resize()
    onScroll()
    // One frame synchronously, before the loop starts. `requestAnimationFrame`
    // does not run in a background tab, so without this the canvas can sit
    // empty until the tab is focused — and on a normal load it removes the
    // flash of nothing between mount and the first animation frame.
    renderer.render(scene, camera)
    observer.observe(host)
    window.addEventListener("resize", resize)
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("pointermove", onPointerMove, { passive: true })
    frame = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener("resize", resize)
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("pointermove", onPointerMove)
      // GPU memory is not garbage collected with the component.
      geometry.dispose()
      for (const leaf of leaves) leaf.material.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [])

  return <div ref={hostRef} className={className} aria-hidden />
}
