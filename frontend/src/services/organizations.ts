import api from "./api"
import type { Course } from "@/types"

export interface OrganizationPerson {
  full_name: string
  avatar_url: string | null
}

export interface OrganizationStats {
  courses: number
  lessons: number
  certificates: number
  /** `null` = not shown (below the privacy threshold or hidden by the organization). */
  members: number | null
  teachers: number | null
}

export interface LockedCourse {
  id: string
  title: string
  image_url: string | null
}

/** `GET /organizations/{slug}` — the page behind `/o/:slug`. */
export interface OrganizationPage {
  slug: string
  public_name: string
  country: string | null
  city: string | null
  active: boolean
  verified: boolean
  description: string | null
  logo_url: string | null
  website_url: string | null
  directors: OrganizationPerson[]
  stats: OrganizationStats
  courses: Course[]
  locked_courses: LockedCourse[]
  viewer_is_member: boolean
  viewer_can_edit: boolean
  /** Present only for a reader who may edit the page. */
  id: string | null
  /** The organization's own setting; present only for a reader who may edit. */
  show_member_count: boolean | null
  since: string
}

export interface OrganizationProfileUpdate {
  description?: string | null
  website_url?: string | null
  show_member_count?: boolean
}

export type OrganizationStatus = "pending" | "approved" | "verified" | "suspended"

/** `GET /admin/organizations` row — the platform's own view. */
export interface AdminOrganization {
  id: string
  slug: string
  public_name: string
  legal_name: string | null
  country: string | null
  status: OrganizationStatus
  verification_basis: string | null
  verified_at: string | null
  created_at: string
  member_count: number
  director_emails: string[]
}

/** `GET /organizations` — one card on the showcase. */
export interface OrganizationCard {
  slug: string
  public_name: string
  country: string | null
  logo_url: string | null
  description: string | null
  courses: number
}

/** `GET /courses/my-organizations` — one block per organization the reader belongs to. */
export interface MyOrganizationCourses {
  organization_id: string
  organization_slug: string
  organization_name: string
  role: "director" | "teacher" | "student"
  courses: Course[]
}

export const organizationsService = {
  async mine(): Promise<MyOrganizationCourses[]> {
    const { data } = await api.get<MyOrganizationCourses[]>("/courses/my-organizations")
    return data
  },

  async list(): Promise<OrganizationCard[]> {
    const { data } = await api.get<OrganizationCard[]>("/organizations")
    return data
  },

  async adminList(): Promise<AdminOrganization[]> {
    const { data } = await api.get<AdminOrganization[]>("/admin/organizations")
    return data
  },

  async adminCreate(body: { slug: string; public_name: string; country?: string; status?: OrganizationStatus }): Promise<AdminOrganization> {
    const { data } = await api.post<AdminOrganization>("/admin/organizations", body)
    return data
  },

  async adminUpdate(
    id: string,
    body: { status?: OrganizationStatus; verification_basis?: string | null },
  ): Promise<AdminOrganization> {
    const { data } = await api.patch<AdminOrganization>(`/admin/organizations/${id}`, body)
    return data
  },

  async adminAppointDirector(id: string, email: string): Promise<AdminOrganization> {
    const { data } = await api.post<AdminOrganization>(`/admin/organizations/${id}/director`, { email })
    return data
  },

  async getPage(slug: string): Promise<OrganizationPage> {
    const { data } = await api.get<OrganizationPage>(`/organizations/${encodeURIComponent(slug)}`)
    return data
  },

  async updateProfile(id: string, body: OrganizationProfileUpdate): Promise<OrganizationPage> {
    const { data } = await api.patch<OrganizationPage>(`/organizations/${id}/profile`, body)
    return data
  },
}
