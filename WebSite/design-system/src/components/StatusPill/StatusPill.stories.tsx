import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusPill } from "./StatusPill";

const meta: Meta<typeof StatusPill> = {
  title: "Primitives/StatusPill",
  component: StatusPill,
  parameters: { layout: "centered" },
  args: { children: "live", kind: "live", pulse: true },
  argTypes: {
    kind: { control: "inline-radio", options: ["live", "idle", "paid", "self", "error"] },
    pulse: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof StatusPill>;

export const Live: Story = { args: { kind: "live", children: "live", pulse: true } };
export const Idle: Story = { args: { kind: "idle", children: "asleep", pulse: false } };
export const Paid: Story = { args: { kind: "paid", children: "paid", pulse: true } };
export const SelfHosted: Story = { args: { kind: "self", children: "self-host", pulse: false } };
export const Error: Story = { args: { kind: "error", children: "error", pulse: false } };

export const AllStates: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      <StatusPill kind="live" pulse>live</StatusPill>
      <StatusPill kind="idle">asleep</StatusPill>
      <StatusPill kind="paid" pulse>paid</StatusPill>
      <StatusPill kind="self">self-host</StatusPill>
      <StatusPill kind="error">error</StatusPill>
    </div>
  ),
};
