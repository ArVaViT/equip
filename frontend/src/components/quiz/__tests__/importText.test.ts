import { describe, expect, it } from "vitest"
import { parseQuestionsText } from "../editor/importText"

/** A test pasted from Word becomes questions, or says which one to fix. */
describe("parseQuestionsText", () => {
  it("reads the Aiken shape, Latin letters and an answer line", () => {
    const [b] = parseQuestionsText("Who wrote Acts?\nA. Peter\nB. Luke\nC. Paul\nANSWER: B")
    expect(b!.question).toEqual({
      question_text: "Who wrote Acts?",
      options: [
        { option_text: "Peter", is_correct: false },
        { option_text: "Luke", is_correct: true },
        { option_text: "Paul", is_correct: false },
      ],
    })
  })

  it("reads Cyrillic letters with brackets, and the answer named in Cyrillic", () => {
    const [b] = parseQuestionsText("Кто написал Деяния?\nА) Пётр\nБ) Лука\nВ) Павел\nОтвет: Б")
    expect(b!.question!.options.map((o) => o.is_correct)).toEqual([false, true, false])
  })

  it("finds the right option marked with a star, before or after", () => {
    const [x, y] = parseQuestionsText("Q1\nA. one\n*B. two\n\nQ2\nA. one *\nB. two")
    expect(x!.question!.options.map((o) => o.is_correct)).toEqual([false, true])
    expect(x!.question!.options[1]!.option_text).toBe("two")
    expect(y!.question!.options.map((o) => o.is_correct)).toEqual([true, false])
    expect(y!.question!.options[0]!.option_text).toBe("one")
  })

  it("keeps a question that runs over two lines, and an option wrapped onto the next", () => {
    const [b] = parseQuestionsText(
      "Согласно Деяниям 2,\nсколько человек крестилось?\nA. Около трёх тысяч\nB. Двенадцать, как\nапостолов\nANSWER: A",
    )
    expect(b!.question!.question_text).toBe("Согласно Деяниям 2,\nсколько человек крестилось?")
    expect(b!.question!.options[1]!.option_text).toBe("Двенадцать, как апостолов")
  })

  it("separates questions by blank lines and survives Windows line ends and no-break spaces", () => {
    const blocks = parseQuestionsText("Q1\r\nA. a\r\nB. b\r\nANSWER: A\r\n\r\n\r\nQ2\nA. x\nB. y\nANSWER: b")
    expect(blocks).toHaveLength(2)
    expect(blocks.every((b) => b.question)).toBe(true)
    expect(blocks[1]!.question!.options[0]!.option_text).toBe("x")
  })

  it("says what is wrong with a block instead of dropping it", () => {
    const problems = parseQuestionsText(
      ["Just a sentence.", "Q\nA. only one\nANSWER: A", "Q\nA. a\nB. b", "Q\nA. a\nB. b\nANSWER: D", "Q\n*A. a\n*B. b"].join("\n\n"),
    ).map((b) => b.problem)
    expect(problems).toEqual(["no_options", "one_option", "no_answer", "answer_not_an_option", "two_answers"])
  })

  it("does not take a question that starts with a letter and a word for an option", () => {
    const [b] = parseQuestionsText("А что сказал Пётр?\nА. Покайтесь\nБ. Молчите\nОтвет: А")
    expect(b!.question!.question_text).toBe("А что сказал Пётр?")
    expect(b!.question!.options[0]!.is_correct).toBe(true)
  })

  it("splits questions pasted from Word with no blank line between them", () => {
    const blocks = parseQuestionsText("Q1?\nA. x\nB. y\nANSWER: A\nQ2?\nA. p\nB. q\nANSWER: B")
    expect(blocks.map((b) => b.question?.question_text)).toEqual(["Q1?", "Q2?"])
    expect(blocks[0]!.question!.options.map((o) => [o.option_text, o.is_correct])).toEqual([
      ["x", true],
      ["y", false],
    ])
    expect(blocks[1]!.question!.options.map((o) => o.is_correct)).toEqual([false, true])
  })

  it("splits starred questions with no blank line when the letters start again", () => {
    const blocks = parseQuestionsText("Q1?\nA. x\n*B. y\nQ2?\n*A. p\nB. q")
    expect(blocks.map((b) => b.question?.question_text)).toEqual(["Q1?", "Q2?"])
    expect(blocks[0]!.question!.options[1]!.option_text).toBe("y")
  })

  it("reads an option with no space after the letter", () => {
    const [b] = parseQuestionsText("Q?\nA.Peter\nB. Luke\nC. Paul\nANSWER: A")
    expect(b!.question!.options.map((o) => [o.option_text, o.is_correct])).toEqual([
      ["Peter", true],
      ["Luke", false],
      ["Paul", false],
    ])
  })

  it("never moves the answer to a neighbour in the same alphabet", () => {
    const [b] = parseQuestionsText("Q?\nB. Luke\nC. Paul\nANSWER: A")
    expect(b!.problem).toBe("answer_not_an_option")
  })

  it("refuses to choose between two answers, or a star and an answer that disagree", () => {
    const problems = parseQuestionsText("Q\nA. a\nB. b\nC. c\nANSWER: B, C\n\nQ\n*A. a\nB. b\nANSWER: B").map((b) => b.problem)
    expect(problems).toEqual(["two_answers", "two_answers"])
  })
})
