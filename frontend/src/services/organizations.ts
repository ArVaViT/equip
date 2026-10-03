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

export const organizationsService = {
  async getPage(slug: string): Promise<OrganizationPage> {
    const { data } = await api.get<OrganizationPage>(`/organizations/${encodeURIComponent(slug)}`)
    return data
  },

  async updateProfile(id: string, body: OrganizationProfileUpdate): Promise<OrganizationPage> {
    const { data } = await api.patch<OrganizationPage>(`/organizations/${id}/profile`, body)
    return data
  },
}
