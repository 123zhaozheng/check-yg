/**
 * 智行卫士品牌 logo —— 简约线条盾牌 + 对勾（守护 / 审查通过）。
 * 单色：使用 currentColor，由父级 className 控制尺寸与颜色。
 */
export function ShieldLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M12 2 L4.5 4.8 V11 C4.5 16 7.8 20.2 12 22 C16.2 20.2 19.5 16 19.5 11 V4.8 Z"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path
        d="M8 12 L11 15 L16 9"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
