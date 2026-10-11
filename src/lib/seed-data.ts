import { Post, Comment } from './types';

export const INITIAL_POSTS: Post[] = [
  {
    id: 'post-1',
    slug: 'lost-art-of-digital-craftsmanship',
    title: 'The Lost Art of Digital Craftsmanship in an Age of Automated Abstraction',
    excerpt: 'When software can be generated with a single prompt, what remains sacred is intentionality, tactile feedback, and the friction that breeds genuine nuance.',
    content: `## The Illusion of Frictionless Production

In the early decades of industrial furniture making, master carpenters noticed an unsettling phenomenon: as steam-powered lathes lowered the cost of turning wood spindles to zero, the market was flooded with chairs whose decorative turns lacked the subtle swelling and tapering that only human hands and eyes had previously calibrated. The spindles were mathematically symmetrical, yet visually sterile.

We are witnessing an identical inflection point in contemporary digital product development.

When interfaces are synthesized in seconds, the temptation to settle for algorithmic averages becomes almost irresistible. We get software that fulfills the functional contract—the buttons submit, the queries resolve, the modals dismiss—yet communicates none of the devotion, idiosyncratic taste, or tactile poise that separates an enduring instrument from disposable utility.

> "True craftsmanship is not merely the absence of flaws, but the presence of care so acute that it leaves an indelible warmth in the artifact itself."

### The Three Hallmarks of Digital Craft

To reclaim craftsmanship from commoditized velocity, we must reconsider what it means to build software as an authored craft:

1. **Rhythmic Typography and Proportional Space**  
   Type is not merely a legible container for words; it is the physical architecture of the reading eye. When hierarchy respects modular scales and line lengths accommodate the reader's breath, cognitive fatigue evaporates.

2. **Kinetic Weight and Micro-Resonance**  
   A digital button shouldn't feel like a phantom rectangle triggering a network payload. It should possess mass. The subtle depression on pointer-down, the crisp spring on release, and the tactile confirmation through color shift ground the user in a tangible reality.

3. **Graceful Degeneration and Defiance of Fragility**  
   Crafted software does not violently shatter when network latency spikes or a dependency falters. It breathes, preserves user intent, and communicates transparently without technical jargon.

\`\`\`typescript
// Craft is encoded in how we handle the margins of error
export async function resilientSync<T>(action: () => Promise<T>): Promise<T> {
  const start = performance.now();
  try {
    const outcome = await action();
    logTelemetry({ status: 'crystallized', duration: performance.now() - start });
    return outcome;
  } catch (err) {
    preserveLocalDraft();
    throw new DignifiedError('We held your state safe while the link recovers.', err);
  }
}
\`\`\`

### Cultivating an Editorial Eye

The ultimate antidote to digital genericism is not more tools, but fewer, more deliberate ones. As we construct the next generation of publishing platforms, we must refuse the lure of superficial templates. Build things that feel sturdy to touch, honest in their mechanics, and proud of the human intellect behind them.`,
    coverImage: 'https://images.unsplash.com/photo-1507842229451-7f01be8860ee?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Julian Vance',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      role: 'Principal Design Technologist',
      bio: 'Investigating typographic rhythm, tactile software interfaces, and the philosophy of digital tools.'
    },
    category: 'Design & Craft',
    tags: ['Craftsmanship', 'Design Systems', 'Philosophy', 'Human Computer Interaction'],
    readTimeMinutes: 6,
    views: 1420,
    claps: 384,
    status: 'published',
    isFeatured: true,
    createdAt: '2026-10-08T09:30:00.000Z',
    updatedAt: '2026-10-08T09:30:00.000Z'
  },
  {
    id: 'post-2',
    slug: 'architecting-for-resonance-fast-software',
    title: 'Architecting for Resonance: Why Fast Software Feels Like Physical Architecture',
    excerpt: 'Sub-50ms latency is not just an engineering benchmark; it alters human cognition and transforms digital software from an errand into an instrument.',
    content: `## The Cognitive Threshold of 100 Milliseconds

In 1968, Robert Miller published a seminal paper on response times in conversational transactions with information systems. His finding remains unshaken after half a century: when an interface acknowledges user input within 100 milliseconds, the human mind attributes the response directly to its own motor action. 

Cross that threshold to 300 milliseconds, and the illusion of direct physical control dissolves. The tool becomes an intermediary, an external bureaucrat you must wait upon.

### The Physics of Perceived Weight

Why does a fountain pen feel fundamentally different than a stylus on cheap capacitive glass? Resistance, instant ink deposition, and the acoustic feedback of metal against parchment.

When we architect modern web applications, speed is the equivalent of ink viscosity. If a state mutation requires three server roundtrips before updating the UI, the application feels like wading through wet cement.

\`\`\`bash
# Latency budget comparison
Input Event -> Local Render:        < 8ms  (Immediate sensory anchor)
Optimistic Mutation Resolution:    < 35ms (Feels instant)
Background Ledger Synchronization:  Async  (Invisible to perception)
\`\`\`

### Architectural Strategies for Resonance

To achieve this level of physical resonance in a web-native publication:

- **Optimistic State with Reversible Rollbacks**: Update counters, likes, and comment threads instantly on pointer press, reconciling with the database in parallel.
- **Micro-caching and Prefetching Boundaries**: Anticipate navigational gestures on hover or viewport intersection before the user clicks.
- **Zero-Layout Shift Typography**: Reserve exact line heights and aspect ratios before web fonts and imagery resolve.

When these disciplines converge, software stops feeling like a website. It becomes a resonant instrument.`,
    coverImage: 'https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Elena Rostova',
      avatar: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&q=80',
      role: 'Staff Systems Architect',
      bio: 'Obsessed with distributed latency, local-first protocols, and mechanical sympathy.'
    },
    category: 'Technology',
    tags: ['Performance', 'Architecture', 'Latency', 'Systems'],
    readTimeMinutes: 5,
    views: 980,
    claps: 247,
    status: 'published',
    isFeatured: false,
    createdAt: '2026-10-09T14:15:00.000Z',
    updatedAt: '2026-10-09T14:15:00.000Z'
  },
  {
    id: 'post-3',
    slug: 'the-computational-garden-rethinking-publishing',
    title: 'The Computational Garden: Rethinking Personal Publishing Beyond the Feed',
    excerpt: 'The algorithmic stream favors ephemeral outrage over cumulative synthesis. A digital garden treats writing as living, evolving foliage.',
    content: `## Streams vs. Topologies

The modern social internet is organized around the chronological stream—an unrelenting conveyor belt where thoughts are published, amplified for twelve hours, and drowned beneath subsequent waves of chatter.

In contrast, the classic blogosphere and personal web operated like an arboretum. You did not publish to "win an algorithm"; you cultivated essays that connected horizontally across years, updating theses as new evidence emerged.

> "A stream is consumed; a garden is traversed. One leaves you breathless, the other leaves you grounded."

### Reviving the Blogspot Heritage

The early days of Blogspot and independently hosted spaces gave writers two essential freedoms that algorithmic platforms stripped away:

1. **Permanence of Address**: Every idea earned a persistent URI that did not degrade into link-rot or walled-garden logins.
2. **Freedom of Structural Expression**: The layout reflected the author’s idiosyncratic intellectual filing system—deep archives, topical labels, curated sidebars, and direct reader dialogue.

By uniting modern full-stack frameworks with this classic ethos, we can build publishing platforms that honor long-form contemplation rather than addictive dopamine loops.`,
    coverImage: 'https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Julian Vance',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      role: 'Principal Design Technologist',
      bio: 'Investigating typographic rhythm, tactile software interfaces, and the philosophy of digital tools.'
    },
    category: 'Culture & Web',
    tags: ['Digital Gardens', 'Web History', 'Blogging', 'IndieWeb'],
    readTimeMinutes: 4,
    views: 812,
    claps: 195,
    status: 'published',
    isFeatured: false,
    createdAt: '2026-10-10T08:00:00.000Z',
    updatedAt: '2026-10-10T08:00:00.000Z'
  },
  {
    id: 'post-4',
    slug: 'beyond-determinism-agents-and-intuition',
    title: 'Beyond Determinism: What Autonomous Agents Teach Us About Human Intuition',
    excerpt: 'When machines can parse probability spaces faster than formal logic, our understanding of human judgment undergoes a radical recalibration.',
    content: `## The Shifting Boundary of Competence

For two centuries, Western education and engineering treated analytical breakdown as the pinnacle of human intellect: take a complex challenge, dissect it into deterministic subroutines, verify each step, and assemble the proof.

Yet modern probabilistic models invert this hierarchy. They thrive precisely where deterministic specifications stumble: ambiguity, style, linguistic nuance, and associative memory.

### The Role of Taste in the Agentic Epoch

If code generation and syntactic execution are now commoditized, what constitutes high leverage for the software architect?

The answer is **Taste and Judgment**. The ability to recognize what *not* to build. The instinct to discard nine plausible solutions in pursuit of the one that possesses structural grace and ethical coherence.

\`\`\`typescript
interface HumanAgentSymbiosis {
  generativeEngine: 'Stochastic synthesis of millions of latent patterns';
  humanConductor: 'Relentless editorial selection and ethical grounding';
  resultantWork: 'Excellence achieved through recursive refinement';
}
\`\`\`

We are no longer solo typists in an empty terminal; we are conductors orchestrating symphonies of probabilistic intelligence.`,
    coverImage: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Marcus K. Sterling',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=200&q=80',
      role: 'Fellow at Cognitive Systems Institute',
      bio: 'Writing on symbolic reasoning, epistemology of artificial neural networks, and generative futures.'
    },
    category: 'Artificial Intelligence',
    tags: ['AI', 'Epistemology', 'Intuition', 'Future of Work'],
    readTimeMinutes: 7,
    views: 1250,
    claps: 412,
    status: 'published',
    isFeatured: false,
    createdAt: '2026-10-10T16:45:00.000Z',
    updatedAt: '2026-10-10T16:45:00.000Z'
  },
  {
    id: 'post-5',
    slug: 'typography-of-thought-letterforms-technical-discourse',
    title: 'The Typography of Thought: How Letterforms Shape Technical Discourse',
    excerpt: 'An exploration of serifs, monospace ligatures, and optical sizing in shaping how engineers and thinkers comprehend complex technical treatises.',
    content: `## The Optical Anatomy of Reading Code and Prose

We often imagine that technical comprehension is purely semantic—that the brain extracts meaning indifferent to the visual rhythm of the glyphs before it.

Empirical ocular tracking tells an entirely different story.

When a reader encounters a high-contrast serif typeface like Newsreader or Baskerville for long-form narrative, the horizontal serifs create an optical shelf that guides saccadic jumps along the line of text. Conversely, for monospace environments, strict horizontal rhythm permits instant vertical scanning for alignment and syntax symmetry.

### The Dual-Register Layout

In Chronicle, we establish a deliberate dual-register typographic architecture:

- **The Editorial Serif Register**: Evoking the weight, deliberation, and gravitas of classic broadside monographs and literary quarterlies.
- **The Precision Monospace Register**: Providing unflinching clarity for metadata, timestamps, telemetry, and source code excerpts.

When these two voices sing in harmony, technical documentation ceases to feel like a spreadsheet and elevates into literature.`,
    coverImage: 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Julian Vance',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80',
      role: 'Principal Design Technologist',
      bio: 'Investigating typographic rhythm, tactile software interfaces, and the philosophy of digital tools.'
    },
    category: 'Design & Craft',
    tags: ['Typography', 'Editorial Design', 'Readability', 'Letterforms'],
    readTimeMinutes: 5,
    views: 640,
    claps: 178,
    status: 'published',
    isFeatured: false,
    createdAt: '2026-10-11T10:10:00.000Z',
    updatedAt: '2026-10-11T10:10:00.000Z'
  },
  {
    id: 'post-6',
    slug: 'local-first-realities-surviving-cloud-decay',
    title: 'Local-First Realities: Surviving the Cloud’s Slow Disintegration',
    excerpt: 'Centralized platforms quietly deprecate, lock out accounts, and suffer bitrot. Why owning your local data files remains the ultimate safeguard.',
    content: `## The Cloud Was Never a Vault

Every developer of a certain vintage remembers the death of Google Reader, the deprecation of beloved APIs, and the sudden sunsetting of cloud note-taking startups that were once venture-backed darlings.

Data stored exclusively on someone else’s remote server is not an asset; it is a temporary lease subject to unilateral eviction.

### The Principles of Local-First Sovereignty

1. **The Primary Source of Truth Lives on Your Machine**: The local SQLite database, JSON file, or plain Markdown folder is authoritative.
2. **Network is an Opportunistic Sync Vector**: If your Wi-Fi fails in a train tunnel, you can still read, draft, edit, and organize without a spinner modal blocking your keyboard.
3. **Open, Inspectable Formats**: Your thoughts should be readable 30 years from now using simple text parsers, without proprietary binaries.

Chronicle adheres strictly to this philosophy: the entire journal's posts and discourse reside in an inspectable, atomic local data layer that can be backed up with a single command.`,
    coverImage: 'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1600&q=80',
    author: {
      name: 'Elena Rostova',
      avatar: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&q=80',
      role: 'Staff Systems Architect',
      bio: 'Obsessed with distributed latency, local-first protocols, and mechanical sympathy.'
    },
    category: 'Technology',
    tags: ['Local First', 'Data Sovereignty', 'Open Source', 'Architecture'],
    readTimeMinutes: 6,
    views: 755,
    claps: 220,
    status: 'published',
    isFeatured: false,
    createdAt: '2026-10-11T12:00:00.000Z',
    updatedAt: '2026-10-11T12:00:00.000Z'
  }
];

export const INITIAL_COMMENTS: Comment[] = [
  {
    id: 'comm-1',
    postId: 'post-1',
    authorName: 'Sarah Jenkins',
    authorEmail: 'sarah.j@example.com',
    authorAvatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=100&q=80',
    content: 'The comparison between steam lathe wood spindles and generative UI is profoundly accurate. We are churning out symmetrical yet lifeless web pages at scale right now.',
    createdAt: '2026-10-08T14:20:00.000Z',
    likes: 24
  },
  {
    id: 'comm-2',
    postId: 'post-1',
    authorName: 'David Chen',
    authorEmail: 'david@craftcode.io',
    authorAvatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=100&q=80',
    content: 'That quote on craftsmanship leaving an indelible warmth... bookmarking this entire essay. The typography on this blog alone proves the point!',
    createdAt: '2026-10-08T18:05:00.000Z',
    likes: 18
  },
  {
    id: 'comm-3',
    postId: 'post-2',
    authorName: 'Nadia Thorne',
    authorEmail: 'nadia@systems.net',
    authorAvatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=100&q=80',
    content: 'Robert Miller’s 100ms rule should be etched onto every frontend developer’s monitor. When a button click takes 350ms to acknowledge, my train of thought derails completely.',
    createdAt: '2026-10-09T16:30:00.000Z',
    likes: 31
  }
];
