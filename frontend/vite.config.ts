import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    exclude: [...configDefaults.exclude, '**/._*'],
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
