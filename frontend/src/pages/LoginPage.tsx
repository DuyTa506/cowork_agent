import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Icon } from '../components/Icon'
import { Input } from '../components/Input'
import { ThemeToggle } from '../components/layout/ThemeToggle'
import { usePageMeta } from '../hooks/usePageMeta'

/** Concentric rings and spokes behind the brand panel (decorative). */
function Pattern() {
  return (
    <svg className="login__pattern" viewBox="0 0 800 800" preserveAspectRatio="xMaxYMin slice" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1">
        {Array.from({ length: 16 }, (_, index) => (
          <circle key={index} cx="640" cy="160" r={50 + index * 46} />
        ))}
        {Array.from({ length: 24 }, (_, index) => {
          const angle = (index / 24) * Math.PI * 2
          return <line key={index} x1={640 + Math.cos(angle) * 50} y1={160 + Math.sin(angle) * 50} x2={640 + Math.cos(angle) * 740} y2={160 + Math.sin(angle) * 740} />
        })}
      </g>
    </svg>
  )
}

/** Sign-in form. There is no self-registration: accounts are created by an administrator. */
export function LoginPage() {
  usePageMeta({ title: 'Đăng nhập' })
  const { status, login } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [capsLock, setCapsLock] = useState(false)

  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from && from !== '/dang-nhap' ? from : '/kho'} replace />
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không đăng nhập được.')
      setBusy(false)
    }
  }
  const watchCaps = (event: KeyboardEvent<HTMLInputElement>) => setCapsLock(event.getModifierState('CapsLock'))

  return (
    <div className="login">
      <section className="login__brand" aria-label="Giới thiệu hệ thống">
        <Pattern />
        <img className="login__watermark" src="/logo-512.png" alt="" />
        <img className="login__org-logo" src="/logo-128.png" width={72} height={72} alt="Biểu tượng Quân khu 3" />
        <div className="login__hero">
          <h2 className="login__headline">Hệ thống AI <span>Quân khu 3</span></h2>
          <p className="login__lead">Hỗ trợ xử lý văn bản</p>
        </div>
      </section>

      <main className="login__panel" id="main">
        <ThemeToggle className="login__theme" />
        <div className="login__card">
          <div className="login__head">
            <h1 className="login__title">Đăng nhập</h1>
          </div>
          <form className="form login__form" onSubmit={submit} noValidate>
            {error && <Alert kind="error" title="Không đăng nhập được">{error}</Alert>}
            <Field label="Tên đăng nhập">
              {({ id, describedBy }) => (
                <Input id={id} icon="user" size="lg" autoComplete="username" autoFocus autoCapitalize="none" spellCheck={false} aria-describedby={describedBy} value={username} onChange={(event) => setUsername(event.target.value)} required />
              )}
            </Field>
            <Field label="Mật khẩu">
              {({ id, describedBy }) => (
                <>
                  <Input
                    id={id}
                    icon="lock"
                    size="lg"
                    type="password"
                    revealable
                    autoComplete="current-password"
                    aria-describedby={describedBy}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    onKeyDown={watchCaps}
                    onKeyUp={watchCaps}
                    onBlur={() => setCapsLock(false)}
                    required
                  />
                  {capsLock && (
                    <div className="login__caps" role="status"><Icon name="capsLock" size={14} />Đang bật Caps Lock</div>
                  )}
                </>
              )}
            </Field>
            <Button variant="primary" size="lg" block type="submit" loading={busy} disabled={!username || !password}>
              {busy ? 'Đang đăng nhập' : 'Đăng nhập'}
            </Button>
          </form>
        </div>
      </main>
    </div>
  )
}
