import { cn } from '../utils/cn'

interface BrandProps {
  size?: 'sm' | 'lg'
  className?: string
}

/**
 * The POTENCIA mark plus wordmark.
 *
 * The supplied artwork is a wide lockup containing the monogram, the wordmark
 * and the tagline. Rendered at header height the lockup is illegible, so the
 * monogram is cropped out as a standalone mark and the wordmark is set in type
 * beside it — one brand, two sizes, no stretched or clipped image. The full
 * lockup is used where there is room for it (the hero and the README).
 */
export function Brand({ size = 'sm', className }: BrandProps) {
  const markHeight = size === 'lg' ? 'h-14' : 'h-9'
  const wordmark = size === 'lg' ? 'text-2xl tracking-[0.32em]' : 'text-base tracking-[0.3em]'

  return (
    <span className={cn('inline-flex select-none items-center gap-2.5', className)}>
      <img
        src="/mark.png"
        alt=""
        aria-hidden="true"
        draggable={false}
        className={cn(
          'w-auto rounded-lg ring-1 ring-line/60',
          markHeight,
        )}
      />
      <span className={cn('font-semibold leading-none text-ink', wordmark)}>POTENCIA</span>
    </span>
  )
}
