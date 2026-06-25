import type { Meta, StoryObj } from "@storybook/react-vite";
import { Ladder } from "./Ladder";

const honestRungs = [
  { name: "Local build", description: "Package compiles from source." },
  { name: "Rendered proof", description: "Storybook renders the component state." },
  { name: "Live user path", description: "A real user surface has exercised it cleanly." },
  { name: "Post-fix evidence", description: "Fresh production evidence exists after the change." },
];

const meta: Meta<typeof Ladder> = {
  title: "Primitives/Ladder",
  component: Ladder,
  parameters: { layout: "centered" },
  args: { start: "outcome", rungs: honestRungs, compact: false },
  argTypes: {
    start: { control: "text" },
    compact: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof Ladder>;

export const Default: Story = { args: { rungs: honestRungs } };
export const Lit: Story = {
  args: {
    rungs: [
      { name: "Local build", description: "Package compiles from source.", lit: true, evidence_url: "#build" },
      { name: "Rendered proof", description: "Storybook renders the component state." },
      { name: "Live user path", description: "A real user surface has exercised it cleanly." },
    ],
  },
};
export const Compact: Story = {
  args: {
    compact: true,
    rungs: [
      { name: "Build", lit: true, evidence_url: "#build" },
      { name: "Storybook" },
      { name: "Live proof" },
      { name: "User evidence" },
    ],
  },
};
