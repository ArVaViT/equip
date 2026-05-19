import type { Certificate } from "@/types"

// ``student_name`` / ``course_title`` / ``student_email`` now live on
// ``Certificate`` itself (populated by the backend's pending-cert
// listing endpoints). Kept as a type alias so existing imports stay
// valid while the underlying shape converges.
export type PendingCert = Certificate
