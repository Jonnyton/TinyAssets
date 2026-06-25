import type { Preview } from "@storybook/react-vite";
// Load the full Field Notes base layer so every story renders on the real
// paper ground with real tokens.
import "../src/styles/base.css";

const preview: Preview = {
  parameters: {
    backgrounds: { disable: true },
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
  },
};
export default preview;
