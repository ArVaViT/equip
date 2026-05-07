import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import PageSpinner from "@/components/ui/PageSpinner"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { ArrowLeft, Users, TrendingUp, Award, Calendar, BarChart3, ClipboardList, UserCheck } from "lucide-react"
import { ErrorState } from "@/components/patterns"
import { formatDate } from "@/i18n/format"

interface AnalyticsEnrollment {
  user_id: string
  progress: number
  enrolled_at: string
  full_name?: string | null
  email?: string
  student?: { id: string; full_name: string | null; email: string }
}

interface AnalyticsRaw {
  total_students?: number
  totalStudents?: number
  enrollments: AnalyticsEnrollment[]
  avg_progress?: number
  avgProgress?: number
  completion_count?: number
  completedCount?: number
  course_title?: string
}

interface Analytics {
  totalStudents: number
  enrollments: AnalyticsEnrollment[]
  avgProgress: number
  completedCount: number
}

export default function TeacherAnalytics() {
  const { courseId } = useParams<{ courseId: string }>()
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [courseTitle, setCourseTitle] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    setLoading(true)
    setAnalytics(null)
    setCourseTitle("")
    const load = async () => {
      try {
        const raw = (await coursesService.getCourseAnalyticsAPI(courseId)) as AnalyticsRaw
        if (cancelled) return
        setAnalytics({
          totalStudents: raw.total_students ?? raw.totalStudents ?? 0,
          enrollments: raw.enrollments ?? [],
          avgProgress: raw.avg_progress ?? raw.avgProgress ?? 0,
          completedCount: raw.completion_count ?? raw.completedCount ?? 0,
        })
        setCourseTitle(raw.course_title ?? "Course")
      } catch {
        // analytics remains null — fallback UI handles this
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [courseId])

  const enrolledThisMonth = analytics?.enrollments.filter((e) => {
    if (!e.enrolled_at) return false
    const d = new Date(e.enrolled_at)
    if (isNaN(d.getTime())) return false
    const now = new Date()
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  }).length ?? 0

  if (loading) {
    return <PageSpinner />
  }

  if (!analytics) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <ErrorState
          icon={<BarChart3 />}
          title="Failed to load analytics"
          action={
            <Link to="/teacher">
              <Button variant="ghost">
                <ArrowLeft className="h-4 w-4 mr-1.5" />
                Back to courses
              </Button>
            </Link>
          }
        />
      </div>
    )
  }

  const stats = [
    { label: "Total Students", value: analytics.totalStudents, icon: Users },
    { label: "Average Progress", value: `${analytics.avgProgress}%`, icon: TrendingUp },
    { label: "Completed (100%)", value: analytics.completedCount, icon: Award },
    { label: "Enrolled This Month", value: enrolledThisMonth, icon: Calendar },
  ]

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <div className="flex items-center gap-3 mb-8">
        <Link to="/teacher">
          <Button variant="ghost" size="icon" className="shrink-0" aria-label="Back to dashboard">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <BarChart3 className="h-7 w-7 text-primary" />
            Course Analytics
          </h1>
          {courseTitle && (
            <p className="text-muted-foreground mt-1">{courseTitle}</p>
          )}
        </div>
        <Link to={`/teacher/courses/${courseId}/progress`}>
          <Button size="sm" variant="outline">
            <UserCheck className="h-4 w-4 mr-1.5" />
            Student Progress
          </Button>
        </Link>
        <Link to={`/teacher/courses/${courseId}/gradebook`}>
          <Button size="sm" variant="outline">
            <ClipboardList className="h-4 w-4 mr-1.5" />
            Gradebook
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">{s.label}</p>
                  <p className="text-2xl font-bold mt-1">{s.value}</p>
                </div>
                <s.icon className="h-8 w-8 text-muted-foreground/60" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Student Enrollments</CardTitle>
          <CardDescription>
            {analytics.totalStudents} student{analytics.totalStudents !== 1 && "s"} enrolled
          </CardDescription>
        </CardHeader>
        <CardContent>
          {analytics.enrollments.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              No students have enrolled yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-3 font-medium text-muted-foreground">Name</th>
                    <th className="pb-3 font-medium text-muted-foreground">Email</th>
                    <th className="pb-3 font-medium text-muted-foreground">Progress</th>
                    <th className="pb-3 font-medium text-muted-foreground">Enrolled</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.enrollments.map((e) => (
                    <tr key={e.user_id} className="border-b last:border-0">
                      <td className="py-3 font-medium">
                        {e.full_name ?? e.student?.full_name ?? "Unknown"}
                      </td>
                      <td className="py-3 text-muted-foreground">
                        {e.email ?? e.student?.email ?? "—"}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-3">
                          <div className="flex-1 h-2 rounded-full bg-muted max-w-[140px]">
                            <div
                              className="h-full rounded-full bg-primary transition-all"
                              style={{ width: `${Math.min(e.progress, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium tabular-nums w-10 text-right">
                            {e.progress}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 text-muted-foreground">
                        {e.enrolled_at ? formatDate(e.enrolled_at) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
