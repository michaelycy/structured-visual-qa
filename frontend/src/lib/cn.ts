import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

const mergeTailwindClasses = extendTailwindMerge({
  prefix: "tw",
  extend: {
    theme: {
      spacing: ["qa-0-5", "qa-1", "qa-2", "qa-3", "qa-4", "qa-5", "qa-6", "qa-8", "qa-10"],
      radius: ["qa-xs", "qa-sm", "qa-md", "qa-lg", "qa-full"],
      text: ["qa-caption", "qa-body", "qa-title"],
      shadow: ["qa-card"],
    },
  },
})

/** 合并条件类名，并按项目的 tw: 前缀规则消除 Tailwind CSS 冲突。 */
export function cn(...inputs: ClassValue[]) {
  return mergeTailwindClasses(clsx(inputs))
}
