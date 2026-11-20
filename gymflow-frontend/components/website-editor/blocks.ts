import type { BlockType, SiteBlock } from "@/types";

export type FieldKind = "text" | "textarea" | "url" | "boolean" | "list-url" | "timings" | "testimonials";

export interface BlockMeta {
  label: string;
  description: string;
  fields: { key: string; label: string; kind: FieldKind }[];
  defaults: Record<string, unknown>;
}

export const BLOCKS: Record<BlockType, BlockMeta> = {
  hero: {
    label: "Hero banner",
    description: "Big headline with a call to action",
    fields: [
      { key: "heading", label: "Heading", kind: "text" },
      { key: "subheading", label: "Subheading", kind: "textarea" },
      { key: "ctaText", label: "Button text", kind: "text" },
      { key: "backgroundImage", label: "Background image URL", kind: "url" },
    ],
    defaults: { heading: "Your strongest self starts here", subheading: "", ctaText: "Book a free trial", ctaTarget: "#contact" },
  },
  about: {
    label: "About",
    description: "A few lines about your gym",
    fields: [{ key: "heading", label: "Heading", kind: "text" }, { key: "body", label: "Text", kind: "textarea" }],
    defaults: { heading: "About us", body: "Tell visitors what makes your gym special." },
  },
  plans: {
    label: "Membership plans",
    description: "Live prices from your plans",
    fields: [{ key: "heading", label: "Heading", kind: "text" }],
    defaults: { heading: "Membership plans", live: true },
  },
  trainers: {
    label: "Trainers",
    description: "Live list of your trainers",
    fields: [{ key: "heading", label: "Heading", kind: "text" }],
    defaults: { heading: "Meet our trainers", live: true },
  },
  gallery: {
    label: "Gallery",
    description: "Photos of your gym",
    fields: [{ key: "heading", label: "Heading", kind: "text" }, { key: "images", label: "Image URLs (one per line)", kind: "list-url" }],
    defaults: { heading: "Inside the gym", images: [] },
  },
  testimonials: {
    label: "Testimonials",
    description: "What members say",
    fields: [{ key: "heading", label: "Heading", kind: "text" }, { key: "items", label: "Testimonials", kind: "testimonials" }],
    defaults: { heading: "What our members say", items: [{ quote: "Lost 8 kg in 3 months with the trainers here!", name: "Priya" }] },
  },
  timings: {
    label: "Timings",
    description: "Opening hours",
    fields: [{ key: "heading", label: "Heading", kind: "text" }, { key: "rows", label: "Hours", kind: "timings" }],
    defaults: { heading: "Timings", rows: [{ days: "Mon – Sat", hours: "5:30 AM – 10:30 PM" }] },
  },
  cta: {
    label: "Call to action",
    description: "Colour band with a button",
    fields: [
      { key: "heading", label: "Heading", kind: "text" },
      { key: "subheading", label: "Subheading", kind: "text" },
      { key: "buttonText", label: "Button text", kind: "text" },
    ],
    defaults: { heading: "First week free", subheading: "No joining fee this month.", buttonText: "Claim offer" },
  },
  contact: {
    label: "Contact & lead form",
    description: "Contact details and enquiry form",
    fields: [
      { key: "heading", label: "Heading", kind: "text" },
      { key: "phone", label: "Phone", kind: "text" },
      { key: "email", label: "Email", kind: "text" },
      { key: "address", label: "Address", kind: "textarea" },
      { key: "showLeadForm", label: "Show enquiry form", kind: "boolean" },
    ],
    defaults: { heading: "Get in touch", showLeadForm: true },
  },
};

export function newBlock(type: BlockType): SiteBlock {
  return { id: Math.random().toString(36).slice(2, 10), type, props: structuredClone(BLOCKS[type].defaults) };
}
