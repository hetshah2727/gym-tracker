// Mirrors the FastAPI schemas in gymflow-backend.

export type Role = "platform_admin" | "gym_owner" | "gym_manager" | "trainer" | "member";
export type MemberStatus = "active" | "inactive" | "expired";
export type FitnessGoal = "weight_loss" | "weight_gain" | "maintenance";
export type DietPreference = "veg" | "non_veg" | "eggetarian" | "vegan";
export type Gender = "male" | "female" | "other";
export type MembershipStatus = "active" | "expired" | "cancelled" | "frozen";
export type PaymentStatus = "pending" | "paid" | "overdue" | "failed" | "refunded";
export type PaymentMethod = "cash" | "upi" | "card" | "bank_transfer" | "online";
export type Channel = "whatsapp" | "voice" | "sms" | "email";
export type NotificationStatus = "queued" | "sent" | "failed";
export type AutomationTrigger =
  | "membership_expiring"
  | "membership_expired"
  | "payment_due"
  | "birthday"
  | "inactive_member";
export type DietPlanStatus = "draft" | "approved" | "assigned";
export type LeadStatus = "new" | "contacted" | "converted" | "lost";

export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  gym_id: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Gym {
  id: string;
  name: string;
  slug: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  timezone: string;
  currency: string;
  logo_url: string | null;
  settings: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface TenantSummary extends Gym {
  member_count: number;
  subscription_status: string | null;
  plan_name: string | null;
}

export interface Member {
  id: string;
  gym_id: string;
  user_id: string | null;
  trainer_id: string | null;
  full_name: string;
  phone: string;
  email: string | null;
  gender: Gender | null;
  date_of_birth: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  fitness_goal: FitnessGoal | null;
  diet_preference: DietPreference | null;
  dietary_restrictions: string | null;
  status: MemberStatus;
  joined_on: string;
  notes: string | null;
  created_at: string;
}

export interface Trainer {
  id: string;
  user_id: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  specialization: string | null;
  bio: string | null;
  photo_url: string | null;
  is_active: boolean;
}

export interface MembershipPlan {
  id: string;
  name: string;
  description: string | null;
  duration_days: number;
  price: number;
  is_active: boolean;
}

export interface Membership {
  id: string;
  member_id: string;
  plan_id: string | null;
  start_date: string;
  end_date: string;
  amount: number;
  status: MembershipStatus;
  auto_renew: boolean;
  created_at: string;
  days_left: number | null;
}

export interface Payment {
  id: string;
  member_id: string;
  membership_id: string | null;
  amount: number;
  status: PaymentStatus;
  method: PaymentMethod | null;
  due_date: string | null;
  paid_at: string | null;
  reference: string | null;
  gateway_order_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface Attendance {
  id: string;
  member_id: string;
  check_in_at: string;
  check_out_at: string | null;
  source: string;
}

export interface AutomationRule {
  id: string;
  name: string;
  trigger: AutomationTrigger;
  offset_days: number;
  channel: Channel;
  template: string;
  n8n_workflow: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Notification {
  id: string;
  member_id: string | null;
  channel: Channel;
  recipient: string;
  message: string;
  category: string;
  status: NotificationStatus;
  scheduled_for: string;
  sent_at: string | null;
  attempts: number;
  error: string | null;
  created_at: string;
}

export interface MealItem {
  food: string;
  quantity: string;
  calories: number;
  protein_g: number;
}

export interface Meal {
  name: string;
  time: string;
  items: MealItem[];
}

export interface DietPlan {
  id: string;
  member_id: string;
  title: string;
  goal: FitnessGoal;
  diet_type: DietPreference;
  daily_calories: number;
  macros: { protein_g: number; carbs_g: number; fat_g: number };
  meals: Meal[];
  notes: string | null;
  status: DietPlanStatus;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
}

export interface AffiliateProduct {
  id: string;
  name: string;
  category: string;
  description: string | null;
  image_url: string | null;
  price: number | null;
  source: string;
  external_url: string;
  asin: string | null;
  commission_rate_pct: number;
  is_active: boolean;
}

export interface AffiliateLink {
  id: string;
  product_id: string;
  trainer_id: string | null;
  code: string;
  clicks: number;
  created_at: string;
  share_url: string | null;
}

export interface AffiliateEarnings {
  total_clicks: number;
  total_conversions: number;
  total_sales: number;
  gym_earnings: number;
  trainer_earnings: number;
  pending_earnings: number;
  by_trainer: { trainer_id: string; name: string; earnings: number }[];
}

export type BlockType =
  | "hero"
  | "about"
  | "plans"
  | "trainers"
  | "gallery"
  | "testimonials"
  | "timings"
  | "contact"
  | "cta";

export interface SiteBlock {
  id: string;
  type: BlockType;
  props: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface Website {
  id: string;
  name: string;
  slug: string;
  template: string;
  theme: { primaryColor?: string; font?: string; mode?: "light" | "dark" };
  blocks: SiteBlock[];
  seo: { title?: string; description?: string };
  custom_domain: string | null;
  is_published: boolean;
  published_at: string | null;
  updated_at: string;
}

export interface PublicSite {
  site: Pick<Website, "name" | "slug" | "template" | "theme" | "seo" | "blocks">;
  gym: {
    name: string;
    phone: string | null;
    email: string | null;
    address: string | null;
    city: string | null;
    logo_url: string | null;
    currency: string;
  };
  plans: { id: string; name: string; duration_days: number; price: number; description: string | null }[];
  trainers: { id: string; name: string; specialization: string | null; bio: string | null; photo_url: string | null }[];
}

export interface Lead {
  id: string;
  website_id: string | null;
  name: string;
  phone: string | null;
  email: string | null;
  message: string | null;
  source: string;
  status: LeadStatus;
  created_at: string;
}

export interface Overview {
  total_members: number;
  active_members: number;
  expired_members: number;
  new_members_this_month: number;
  expiring_in_7_days: number;
  revenue_this_month: number;
  revenue_last_month: number;
  pending_amount: number;
  pending_count: number;
  checkins_today: number;
  new_leads: number;
}

export interface PeriodReport {
  period_start: string;
  period_end: string;
  new_members: number;
  active_members: number;
  memberships_expired: number;
  memberships_expiring_next_7_days: number;
  revenue_collected: number;
  payments_collected: number;
  pending_amount: number;
  pending_count: number;
  checkins: number;
  new_leads: number;
}

export interface SubscriptionPlan {
  id: string;
  code: string;
  name: string;
  price_monthly: number;
  max_members: number | null;
  features: Record<string, boolean>;
  is_active: boolean;
}

export interface GymSubscription {
  id: string;
  gym_id: string;
  plan_id: string;
  status: string;
  current_period_end: string;
  plan: SubscriptionPlan | null;
}

export interface PlatformStats {
  total_gyms: number;
  active_gyms: number;
  total_members: number;
  active_members: number;
  mrr: number;
  subscriptions_by_status: Record<string, number>;
  affiliate_platform_earnings: number;
  gym_fee_volume_this_month: number;
}
