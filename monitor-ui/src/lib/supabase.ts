import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL =
  import.meta.env.VITE_SUPABASE_URL || "https://supabase.riztama.my.id";
const SUPABASE_ANON_KEY =
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  "sb_publishable_TuuasLbN1zmVVbD_wmviZ2_pwLKyHYX";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  db: { schema: "proxxies" },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});
