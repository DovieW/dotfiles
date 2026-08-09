import type { SelectOption } from "@opentui/core"

function scoreToken(token: string, candidate: string): number | null {
  let score = 0, previous = -2, cursor = 0
  for (const character of token) {
    const index = candidate.indexOf(character, cursor)
    if (index < 0) return null
    if (index === 0 || " /_.-".includes(candidate[index - 1] || "")) score += 12
    if (index === previous + 1) score += 8
    score -= index - cursor
    previous = index
    cursor = index + 1
  }
  const exact = candidate.indexOf(token)
  if (exact >= 0) score += 40 - Math.min(exact, 20)
  return score
}

export function fuzzyScore(query: string, candidate: string): number | null {
  const normalized = candidate.toLocaleLowerCase()
  const tokens = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean)
  if (!tokens.length) return 0
  let score = 0
  for (const token of tokens) {
    const tokenScore = scoreToken(token, normalized)
    if (tokenScore === null) return null
    score += tokenScore
  }
  return score - Math.floor(normalized.length / 100)
}

export function fuzzyOptions(query: string, items: SelectOption[]): SelectOption[] {
  if (!query.trim()) return items
  return items.map((item, index) => ({
    item, index, score: fuzzyScore(query, `${item.name} ${item.description}`),
  })).filter((entry) => entry.score !== null)
    .sort((left, right) => right.score! - left.score! || left.index - right.index)
    .map((entry) => entry.item)
}
