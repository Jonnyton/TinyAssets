import type { Metadata } from "next";
import HostClient from "./_components/HostClient";

export const metadata: Metadata = {
  title: "Host — run Tiny on your own machine",
  description:
    "You don't have to host anything to use Tiny — the public engine runs 24/7. Hosting is for your own private universes on your own machine: your keys, your data, the same loop pattern pointed at your projects.",
  alternates: { canonical: "https://tinyassets.io/host" },
};

export default function HostPage() {
  return <HostClient />;
}
