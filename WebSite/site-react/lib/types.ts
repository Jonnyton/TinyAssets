export type Edge = { from: string; to: string; kind?: string };

export type Snapshot = {
  fetched_at: string;
  source: string;
  stats: {
    wiki_promoted: number;
    wiki_drafts: number;
    goals: number;
    universes: number;
    edges?: number;
  };
  goals: Array<{
    id: string;
    name: string;
    summary: string;
    tags: string[];
    author: string;
    visibility: string;
  }>;
  universes: Array<{
    id: string;
    phase: string;
    word_count: number;
    last_activity_at: string | null;
    accept_rate: number | null;
  }>;
  wiki: {
    bugs: Array<{ id: string; title: string; slug?: string }>;
    concepts: Array<{ slug: string; title: string }>;
    notes: Array<{ slug: string; title: string }>;
    plans: Array<{ slug: string; title: string }>;
    drafts: Array<{ slug: string; title: string }>;
    other?: Array<{ slug: string; title: string }>;
  };
  edges?: Edge[];
  tags?: Record<string, string[]>;
};
