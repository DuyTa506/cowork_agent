/**
 * Decorative engraved-rosette pattern (the kind printed on banknotes and certificates): rotated ellipses, concentric rings and a
 * five-point star drawn as hairlines. Pure SVG, no external image; meant to sit behind content at very low opacity.
 */
export function GuillochePattern({ className }: { className?: string }) {
  const ellipses = Array.from({ length: 36 }, (_, index) => index * 5)
  const rings = [60, 96, 132, 168, 204, 240, 276, 312]
  const star = starPoints(0, 0, 150, 58)
  return (
    <svg className={className} viewBox="-400 -400 800 800" aria-hidden="true" focusable="false" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke="currentColor" strokeWidth="0.8">
        {ellipses.map((angle) => (
          <ellipse key={angle} rx="360" ry="104" transform={`rotate(${angle})`} />
        ))}
        {ellipses.map((angle) => (
          <ellipse key={`s${angle}`} rx="228" ry="62" transform={`rotate(${angle + 2.5})`} opacity="0.7" />
        ))}
        {rings.map((radius) => (
          <circle key={radius} r={radius} opacity="0.8" />
        ))}
        <polygon points={star} strokeWidth="1.4" />
        <polygon points={star} strokeWidth="1.4" transform="scale(0.62)" />
      </g>
    </svg>
  )
}

function starPoints(cx: number, cy: number, outer: number, inner: number): string {
  const points: string[] = []
  for (let index = 0; index < 10; index += 1) {
    const radius = index % 2 === 0 ? outer : inner
    const angle = (Math.PI / 5) * index - Math.PI / 2
    points.push(`${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`)
  }
  return points.join(' ')
}
