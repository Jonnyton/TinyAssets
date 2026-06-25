import type { Meta, StoryObj } from "@storybook/react-vite";
import { Term } from "./Term";

const meta: Meta<typeof Term> = {
  title: "Primitives/Term",
  component: Term,
  parameters: { layout: "centered" },
  args: { def: "A branch that keeps working without a host process online.", children: "zero-host uptime" },
  argTypes: {
    def: { control: "text" },
    children: { control: "text" },
  },
};
export default meta;

type Story = StoryObj<typeof Term>;

export const Default: Story = {
  render: (args) => (
    <p style={{ maxWidth: 560, lineHeight: 1.6 }}>
      The release is accepted only when <Term {...args} /> is proven through the
      live user path.
    </p>
  ),
};
