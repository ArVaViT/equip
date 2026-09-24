/**
 * A clearing in the scene behind a block of text.
 *
 * The backdrop is translucent `--ink` planes over `--background`, and the
 * page's secondary text is `--ink-muted` — both greys. Wherever the two
 * met, the text sank: a contrast audit over every scroll position, both
 * themes, desktop and phone, found 83 places under 4.5:1 and one at 1.0:1
 * (the first claim's body over the stacked pose). Vadym found that one by
 * eye: «цвет текста и фоновой анимации перекрывается».
 *
 * Moving the poses away from the words fixes the case you can see and not
 * the ones in between two poses. This fixes all of them: a soft radial
 * wash of the page colour behind the block, opaque at its centre and gone
 * well outside it, so the leaves fade out as they approach the words. It
 * reads as light around the text rather than as a box, and it is the same
 * token in both themes, so it cannot be right in one and wrong in the
 * other.
 *
 * Put it on the element that wraps the text; it paints a pseudo-element
 * behind the element's own content and outside its box.
 */
export const TEXT_VEIL =
  "relative isolate before:pointer-events-none before:absolute before:-inset-x-32 before:-inset-y-36 before:-z-10 before:content-[''] before:bg-[radial-gradient(closest-side,hsl(var(--background))_50%,hsl(var(--background)/0.9)_64%,hsl(var(--background)/0.55)_78%,hsl(var(--background)/0.18)_91%,hsl(var(--background)/0))]"
