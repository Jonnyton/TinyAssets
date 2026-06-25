import type { Meta, StoryObj } from "@storybook/react-vite";
import { RitualLabel } from "./RitualLabel";

const meta: Meta<typeof RitualLabel> = {
  title: "Primitives/RitualLabel",
  component: RitualLabel,
  parameters: { layout: "centered" },
  args: { children: "Field note · 001" },
};
export default meta;

type Story = StoryObj<typeof RitualLabel>;

export const Default: Story = {};
export const Ember: Story = { args: { children: "Live evidence", color: "var(--ember-700)" } };
export const Violet: Story = { args: { children: "Lineage", color: "var(--violet-700)" } };
