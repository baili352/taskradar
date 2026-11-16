import type { Evidence } from '../../types'

/** 展示原文证据：位置 + 原文摘录。 */
export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) return null

  return (
    <ul className="evidence-list">
      {evidence.map((item, index) => (
        <li className="evidence-item" key={`${item.location}-${index}`}>
          <span className="evidence-loc">{item.location}</span>
          <p>「{item.text}」</p>
        </li>
      ))}
    </ul>
  )
}
