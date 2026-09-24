/**
 * Vertical on a phone, until there are vertical cuts to show there.
 *
 * Both films are 16:9. On a 390px screen that is a 358×200 strip in the
 * middle of a screen that is otherwise empty — «видео что там есть сделай
 * их вертикальными, просто обрежь, до тех пор пока я не сделаю отдельных
 * видео для телефона». So below `sm` the frame is 9:16 and the picture is
 * cropped to its centre with `object-cover`, which also applies to the
 * poster. The product captions are burnt in at the top centre, which the
 * crop keeps. `max-h` stops it running under the header on a short phone.
 *
 * WHEN THE PHONE CUTS EXIST: give the `<video>` a
 * `<source media="(max-width: 639px)">` for them and delete this.
 */
export const MOBILE_VERTICAL =
  "aspect-[9/16] max-h-[78svh] object-cover object-center sm:aspect-auto sm:max-h-none"
