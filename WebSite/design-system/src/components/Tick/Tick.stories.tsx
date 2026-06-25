import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tick } from "./Tick";

const meta: Meta<typeof Tick> = {
  title: "Primitives/Tick",
  component: Tick,
  parameters: { layout: "centered" },
  args: { label: "source", href: "#source" },
  argTypes: {
    label: { control: "text" },
    href: { control: "text" },
    external: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof Tick>;

export const Default: Story = { args: { label: "source", href: "#source" } };
export const External: Story = {
  args: { label: "field note", href: "https://tinyassets.io", external: true },
};
export const Flat: Story = { args: { label: "observed", href: "" } };
