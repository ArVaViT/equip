import { useEffect } from "react"
import { useLocation } from "react-router-dom"
import { rememberReturnPath } from "@/lib/authRedirect"
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
  const location = useLocation()
  // A confirmation link and Google both come back through /auth/callback.
  useEffect(() => rememberReturnPath(location.state), [location.state])
  const {
    form,
    errors,
    serverError,
    duplicateEmail,
    success,
    loading,
    googleLoading,
    showPassword,
    passwordGenerated,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
    toggleShowPassword,
    handleGeneratePassword,
  } = useRegister()

  if (duplicateEmail) {
    return <DuplicateEmailView email={form.email} />
  }

  if (success) {
    return <SuccessView email={form.email} />
  }

  return (
    <RegisterForm
      form={form}
      errors={errors}
      serverError={serverError}
      loading={loading}
      googleLoading={googleLoading}
      showPassword={showPassword}
      passwordGenerated={passwordGenerated}
      onChange={handleChange}
      onSubmit={handleSubmit}
      onGoogleSignUp={handleGoogleSignUp}
      onToggleShowPassword={toggleShowPassword}
      onGeneratePassword={handleGeneratePassword}
    />
  )
}
