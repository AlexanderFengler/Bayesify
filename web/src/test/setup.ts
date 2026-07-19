// Registers @testing-library/jest-dom's custom matchers (toBeInTheDocument, etc.) on Vitest's expect
// and installs automatic React Testing Library cleanup after each test. Loaded via test.setupFiles in
// vite.config.ts, so every test file gets them without importing anything.
import "@testing-library/jest-dom/vitest";
