interface SkeletonProps {
  /** CSS size or px number. */
  width?: number | string
  height?: number | string
  circle?: boolean
  className?: string
}

/** Shimmering placeholder block. Size it like the content it stands for so nothing jumps when data arrives. */
export function Skeleton({ width = '100%', height = 14, circle, className }: SkeletonProps) {
  return <span className={['skeleton', circle && 'skeleton--circle', className].filter(Boolean).join(' ')} style={{ width, height }} aria-hidden="true" />
}

/** A paragraph of skeleton lines; the last one is shorter. */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <span className="skeleton-text" role="status" aria-label="Đang tải">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} width={index === lines - 1 && lines > 1 ? '60%' : '100%'} />
      ))}
    </span>
  )
}
