import { Node, mergeAttributes } from "@tiptap/core"

export type CalloutVariant = "info" | "verse" | "takeaway" | "warning" | "toggle"

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    callout: {
      setCallout: (attrs?: { variant?: CalloutVariant }) => ReturnType
      toggleCallout: (attrs?: { variant?: CalloutVariant }) => ReturnType
      unsetCallout: () => ReturnType
    }
  }
}

export const Callout = Node.create({
  name: "callout",
  group: "block",
  content: "block+",
  defining: true,

  addAttributes() {
    return {
      variant: {
        default: "info",
        parseHTML: (el) => el.getAttribute("data-callout") || "info",
        renderHTML: (attrs) => ({ "data-callout": attrs.variant }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-callout]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { class: `callout callout-${HTMLAttributes["data-callout"] || "info"}` }),
      0,
    ]
  },

  addCommands() {
    return {
      setCallout:
        (attrs) =>
        ({ commands }) =>
          commands.wrapIn(this.name, attrs),
      toggleCallout:
        (attrs) =>
        ({ commands }) =>
          commands.toggleWrap(this.name, attrs),
      unsetCallout:
        () =>
        ({ commands }) =>
          commands.lift(this.name),
    }
  },
})
