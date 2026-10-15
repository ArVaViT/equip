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
  const r = useRegister()

  if (r.duplicateEmail) {
    return <DuplicateEmailView email={r.form.email} state={location.state} />
  }

  if (r.sent) {
    return <SuccessView email={r.sent.email} repeated={r.sent.repeated} onChangeAddress={r.changeAddress} />
  }

  return (
    <RegisterForm
      form={r.form}
      errors={r.errors}
      serverError={r.serverError}
      loading={r.loading}
      googleLoading={r.googleLoading}
      showPassword={r.showPassword}
      passwordGenerated={r.passwordGenerated}
      onChange={r.handleChange}
      onSubmit={r.handleSubmit}
      onGoogleSignUp={r.handleGoogleSignUp}
      onToggleShowPassword={r.toggleShowPassword}
      onGeneratePassword={r.handleGeneratePassword}
    />
  )
}
