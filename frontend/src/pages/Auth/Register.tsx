import { ROLES } from "@/types"
import { DuplicateEmailView } from "./register/DuplicateEmailView"
import { RegisterForm } from "./register/RegisterForm"
import { SuccessView } from "./register/SuccessView"
import { useRegister } from "./register/useRegister"

/**
 * Top-level /register route. Picks one of three views based on the
 * current `useRegister` state; everything else (validation, mutations,
 * error handling) lives inside the hook and the sibling view components.
 */
export default function Register() {
  const {
    form,
    errors,
    serverError,
    duplicateEmail,
    success,
    loading,
    googleLoading,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
  } = useRegister()

  if (duplicateEmail) {
    return <DuplicateEmailView email={form.email} />
  }

  if (success) {
    return <SuccessView email={form.email} isTeacher={form.role === ROLES.TEACHER} />
  }

  return (
    <RegisterForm
      form={form}
      errors={errors}
      serverError={serverError}
      loading={loading}
      googleLoading={googleLoading}
      onChange={handleChange}
      onSubmit={handleSubmit}
      onGoogleSignUp={handleGoogleSignUp}
    />
  )
}
