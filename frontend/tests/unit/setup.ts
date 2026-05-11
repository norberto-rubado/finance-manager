// Vitest 全局 setup:接入 @testing-library/jest-dom 扩展 matcher(toBeInTheDocument 等)。
// 切片 D 起首次出现 RTL 测试,此处统一注入。
import '@testing-library/jest-dom/vitest';
