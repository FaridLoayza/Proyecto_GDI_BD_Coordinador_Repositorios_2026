import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { BsAward, BsBoxArrowRight, BsBuildings, BsClockHistory, BsClipboard2Check, BsDatabase, BsEye, BsEyeSlash, BsFileEarmarkBarGraph, BsHouseDoor, BsPeople, BsSearch } from 'react-icons/bs'
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import './App.css'

const AuthContext = createContext(null)
const ODS = [
  'ODS 1: Fin de la pobreza', 'ODS 2: Hambre cero', 'ODS 3: Salud y bienestar',
  'ODS 4: Educación de calidad', 'ODS 5: Igualdad de género', 'ODS 6: Agua limpia y saneamiento',
  'ODS 7: Energía asequible y no contaminante', 'ODS 8: Trabajo decente y crecimiento económico',
  'ODS 9: Industria, innovación e infraestructura', 'ODS 10: Reducción de las desigualdades',
  'ODS 11: Ciudades y comunidades sostenibles', 'ODS 12: Producción y consumo responsables',
  'ODS 13: Acción por el clima', 'ODS 14: Vida submarina',
  'ODS 15: Vida de ecosistemas terrestres', 'ODS 16: Paz, justicia e instituciones sólidas',
  'ODS 17: Alianzas para lograr los objetivos',
]
// Lista cerrada de escuelas profesionales de la universidad (debe coincidir con
// ESCUELAS en backend/src/repositorios/catalogos.py).
const ESCUELAS = [
  'Administración de Empresas', 'Arquitectura', 'Ciencia Política y Gobierno',
  'Comunicación Social', 'Contabilidad', 'Derecho', 'Educación Inicial', 'Enfermería',
  'Farmacia y Bioquímica', 'Ingeniería Ambiental', 'Ingeniería Biomédica',
  'Ingeniería Biotecnológica', 'Ingeniería Civil', 'Ingeniería Comercial',
  'Ingeniería de Minas', 'Ingeniería de Sistemas', 'Ingeniería en Inteligencia Artificial',
  'Ingeniería Industrial', 'Ingeniería Mecánica', 'Ingeniería Mecánica Eléctrica',
  'Ingeniería Mecatrónica', 'Medicina Humana', 'Medicina Veterinaria y Zootecnia',
  'Obstetricia y Puericultura', 'Odontología', 'Psicología', 'Publicidad y Multimedia',
  'Tecnología Médica',
]
const FOTO_MAX_BYTES = 2 * 1024 * 1024
const EMPTY_APPLICATION = {
  dni: '', codigo_ucsm: '', correo: '', nombres: '', apellido_paterno: '',
  apellido_materno: '', genero: 'Femenino', fecha_nacimiento: '', escuela: '',
  celular: '', orcid: '', scopus_id: '', link_cti: '', resumen: '', foto: '',
  ods: [], intereses: [],
}

function messageFrom(data) {
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg).join(' · ')
  return data?.detail || 'Ocurrió un error. Intente nuevamente.'
}

async function sendRequest(path, { method = 'GET', body, csrf, headers = {} } = {}) {
  const options = { method, credentials: 'same-origin', headers: { ...headers } }
  if (body !== undefined) {
    if (body instanceof FormData) {
      options.body = body
    } else {
      options.headers['Content-Type'] = 'application/json'
      options.body = JSON.stringify(body)
    }
  }
  if (method !== 'GET' && csrf) options.headers['X-CSRF-Token'] = csrf
  const response = await fetch(path, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(messageFrom(data))
  return data
}

function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [csrf, setCsrf] = useState('')
  const [loading, setLoading] = useState(true)
  const [authError, setAuthError] = useState('')

  useEffect(() => {
    sendRequest('/api/auth/me')
      .then((data) => { setUser(data.user); setCsrf(data.csrf_token); setAuthError('') })
      .catch((error) => setAuthError(`No se pudo conectar con el portal: ${error.message}`))
      .finally(() => setLoading(false))
  }, [])

  const request = useCallback((path, options = {}) => (
    sendRequest(path, { ...options, csrf })
  ), [csrf])
  const signIn = useCallback(async (body) => {
    const data = await sendRequest('/api/auth/login', { method: 'POST', body, csrf })
    setUser(data.user)
    setCsrf(data.csrf_token)
    setAuthError('')
    return data.user
  }, [csrf])
  const register = useCallback(async (body) => {
    const data = await sendRequest('/api/researcher/register', { method: 'POST', body, csrf })
    setUser(null)
    setCsrf(data.csrf_token)
    setAuthError('')
    return data
  }, [csrf])
  const signOut = useCallback(async () => {
    await sendRequest('/api/auth/logout', { method: 'POST', csrf })
    const data = await sendRequest('/api/auth/me')
    setUser(null)
    setCsrf(data.csrf_token)
    setAuthError('')
  }, [csrf])
  const value = useMemo(() => ({
    user, csrf, loading, authError, setUser, request, signIn, register, signOut,
  }), [user, csrf, loading, authError, request, signIn, register, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

function homeFor(role) {
  return { coordinator: '/coordinator', admin: '/admin' }[role] || '/investigator'
}

function useAuth() {
  return useContext(AuthContext)
}

function Brand() {
  return (
    <Link className="brand" to="/" aria-label="Sistema Gestor de Investigación, inicio">
      <img className="brand-logo" src="/assets/cris-horizontal.png" alt="Sistema Gestor de Investigación" />
    </Link>
  )
}

function SidebarBrand({ to }) {
  return (
    <Link className="sidebar-brand" to={to} aria-label="Sistema Gestor de Investigación, inicio">
      <img src="/assets/cris-horizontal-claro.png" alt="Sistema Gestor de Investigación" />
    </Link>
  )
}

function AppFrame({ children }) {
  const { user, signOut, authError } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  async function logout() {
    try { await signOut(); navigate('/') } catch (error) { window.alert(error.message) }
  }
  const links = user?.role === 'admin'
    ? [['/admin', 'Datos (CRUD)', BsDatabase, true]]
    : user?.role === 'coordinator'
    ? [
      ['/coordinator', 'Inicio', BsHouseDoor, true],
      ['/coordinator/applications', 'Bandeja de revisión', BsClipboard2Check],
      ['/coordinator/investigators', 'Investigadores', BsPeople],
      ['/coordinator/registered-patents', 'Patentes', BsAward],
      ['/coordinator/publications', 'Histórico', BsClockHistory],
      ['/coordinator/reports', 'Reportes', BsFileEarmarkBarGraph],
    ]
    : [
      ['/investigator', 'Mi solicitud', BsClipboard2Check, true],
      ...(user?.estado === 'aprobada' ? [['/investigator/patents', 'Mis patentes', BsAward, true]] : []),
    ]
  const topbar = (
    <header className="topbar">
      {user ? (
        <div className="topbar-user">
          <span><strong>{user.nombre || user.correo}</strong><small>{{ coordinator: 'Coordinador', admin: 'Administrador' }[user.role] || 'Investigador'}</small></span>
          <button className="button button-outline button-compact" onClick={logout}><BsBoxArrowRight aria-hidden="true" />Cerrar sesión</button>
        </div>
      ) : <><Brand />{location.pathname !== '/' && <Link className="button button-outline" to="/">Inicio</Link>}</>}
    </header>
  )
  return (
    user ? (
      <div className="app app-authenticated">
        <div className="app-shell">
          <aside className="sidebar">
            <SidebarBrand to={homeFor(user.role)} />
            <nav className="sidebar-nav" aria-label="Menú principal">
              <p className="sidebar-label">MENÚ PRINCIPAL</p>
              {links.map(([href, label, Icon, exact]) => (
                <NavLink key={href} end={exact} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} to={href}>
                  <Icon aria-hidden="true" /><span>{label}</span>
                </NavLink>
              ))}
            </nav>
          </aside>
          <div className="content-area">
            {topbar}
            <main className="main-content">{authError && <Alert kind="error">{authError}</Alert>}{children}</main>
          </div>
        </div>
      </div>
    ) : (
      <div className="app">
        {topbar}
        <main className="public-content">{authError && <Alert kind="error">{authError}</Alert>}{children}</main>
      </div>
    )
  )
}

function RequireRole({ role }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading">Cargando portal…</div>
  if (!user) return <Navigate to="/" replace />
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />
  return <Outlet />
}

function Home() {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading">Cargando portal…</div>
  if (user) return <Navigate to={homeFor(user.role)} replace />
  return (
    <section className="home">
      <div className="hero">
        <h1>Sistema Gestor de Investigación</h1>
      </div>
      <div className="access-grid">
        <article className="access-card">
          <span className="card-kicker">DOCENTES E INVESTIGADORES</span>
          <h2>Acceso de investigador</h2>
          <p>Envía tu postulación, revisa su estado y solicita registros de patente después de la aprobación.</p>
          <div className="actions"><Link className="button button-primary" to="/register">Crear cuenta</Link><Link className="text-link" to="/login/investigator">Ya tengo una cuenta</Link></div>
        </article>
        <article className="access-card">
          <span className="card-kicker">GESTIÓN INSTITUCIONAL</span>
          <h2>Acceso de coordinador</h2>
          <p>Revisa postulaciones, verifica ORCID, registra Pure manualmente y resuelve solicitudes de patente.</p>
          <div className="actions"><Link className="button button-primary" to="/login/coordinator">Ingresar al portal</Link></div>
        </article>
      </div>
      <p className="notice">Las verificaciones de ORCID aportan evidencia, pero no aprueban automáticamente una postulación ni confirman la afiliación institucional.</p>
      <p className="small-muted admin-access-link"><Link className="text-link" to="/login/admin">Acceso de administrador</Link></p>
    </section>
  )
}

const LOGIN_TEXTS = {
  coordinator: ['Gestión institucional', 'Acceso del coordinador', 'Use sus credenciales institucionales.'],
  investigator: ['Acceso de investigador', 'Ingresa a tu cuenta', 'Consulta el estado de tu postulación o perfil.'],
  admin: ['Mantenimiento técnico', 'Acceso de administrador', 'Administración de los datos del portal (CRUD).'],
}

function LoginPage() {
  const { role } = useParams()
  const { user, signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const registered = role === 'investigator' && location.state?.registered
  const [email, setEmail] = useState(() => (registered && location.state?.email) || '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!LOGIN_TEXTS[role]) return <Navigate to="/" replace />
  if (user) return <Navigate to={homeFor(user.role)} replace />
  async function submit(event) {
    event.preventDefault()
    setError(''); setBusy(true)
    try {
      const account = await signIn({ role, email, password })
      navigate(homeFor(account.role))
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return (
    <section className="panel auth-panel">
      <p className="eyebrow">{LOGIN_TEXTS[role][0]}</p>
      <h1>{LOGIN_TEXTS[role][1]}</h1>
      <p className="muted">{LOGIN_TEXTS[role][2]}</p>
      {registered && <Alert kind="success">Tu cuenta fue creada y tu postulación quedó enviada al coordinador. Ya puedes iniciar sesión.</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <form className="form-grid" onSubmit={submit}>
        <TextField label="Correo electrónico" name="email" type="email" value={email} onChange={setEmail} required autoComplete="username" />
        <PasswordField label="Contraseña" name="password" value={password} onChange={setPassword} required autoComplete="current-password" />
        <div className="form-actions"><button className="button button-primary" disabled={busy}>{busy ? 'Ingresando…' : 'Ingresar'}</button><Link className="text-link" to="/">Volver al inicio</Link></div>
      </form>
    </section>
  )
}

function TextField({ label, name, value, onChange, type = 'text', required = false, disabled = false, help, maxLength, min, max, autoComplete }) {
  return (
    <label className="field">
      <span>{label}{required && <b className="required"> *</b>}</span>
      <input name={name} type={type} value={value ?? ''} required={required} disabled={disabled} maxLength={maxLength} min={min} max={max} autoComplete={autoComplete} onChange={(event) => onChange(event.target.value)} />
      {help && <small>{help}</small>}
    </label>
  )
}

function PasswordField({ label, name, value, onChange, required = false, autoComplete, help }) {
  const [visible, setVisible] = useState(false)
  return (
    <label className="field">
      <span>{label}{required && <b className="required"> *</b>}</span>
      <div className="password-input">
        <input
          name={name} type={visible ? 'text' : 'password'} value={value ?? ''} required={required}
          autoComplete={autoComplete} onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button" className="password-toggle"
          aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <BsEyeSlash /> : <BsEye />}
        </button>
      </div>
      {help && <small>{help}</small>}
    </label>
  )
}

function TextArea({ label, value, onChange, required = false, rows = 4, maxLength, help }) {
  return <label className="field field-span"><span>{label}{required && <b className="required"> *</b>}</span><textarea rows={rows} value={value ?? ''} required={required} maxLength={maxLength} onChange={(event) => onChange(event.target.value)} />{help && <small>{help}</small>}</label>
}

function Alert({ kind = 'info', children }) {
  return <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}

// Borrador del formulario guardado antes de salir a orcid.org, para no perder
// lo ya escrito al volver. Las contraseñas nunca se guardan aquí.
const ORCID_DRAFT_KEY = 'cris_form_borrador'

function readDraft(mode) {
  try {
    const draft = JSON.parse(window.sessionStorage.getItem(ORCID_DRAFT_KEY) || 'null')
    return draft && draft.mode === mode ? draft.form : null
  } catch { return null }
}

function saveDraft(mode, form) {
  try { window.sessionStorage.setItem(ORCID_DRAFT_KEY, JSON.stringify({ mode, form })) } catch { /* sin almacenamiento: se pierde el borrador */ }
}

function clearDraft() {
  try { window.sessionStorage.removeItem(ORCID_DRAFT_KEY) } catch { /* nada que limpiar */ }
}

const ORCID_RETURN_MESSAGES = {
  ok: ['success', 'Cuenta ORCID conectada correctamente.'],
  cancelado: ['warning', 'Cancelaste la conexión con ORCID. Puedes intentarlo de nuevo.'],
  error: ['error', 'No se pudo conectar con ORCID. Intenta nuevamente.'],
}

function OrcidConnectField({ form, update, isCorrection }) {
  const { request, csrf } = useAuth()
  const [status, setStatus] = useState(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [returnMessage] = useState(() => ORCID_RETURN_MESSAGES[searchParams.get('orcid')] || null)
  const mode = isCorrection ? 'investigator' : 'register'

  useEffect(() => {
    if (searchParams.has('orcid')) {
      const next = new URLSearchParams(searchParams)
      next.delete('orcid')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  useEffect(() => {
    let active = true
    request('/api/auth/orcid/status').then((data) => {
      if (!active) return
      setStatus(data)
      // Solo el ORCID verificado en el servidor reemplaza al del formulario.
      if (data.orcid) {
        update('orcid', data.orcid)
        update('scopus_id', data.scopus_id ? String(data.scopus_id) : '')
      }
    }).catch(() => active && setStatus({ configurado: false, orcid: null }))
    return () => { active = false }
  }, [request, update])

  function connect() {
    const draft = { ...form }
    delete draft.orcid
    delete draft.scopus_id
    saveDraft(mode, draft)
    window.location.assign(`/api/auth/orcid/login?next=${mode}`)
  }

  async function disconnect() {
    await sendRequest('/api/auth/orcid/disconnect', { method: 'POST', csrf })
    setStatus((current) => ({ ...current, orcid: null, nombre: null, scopus_id: null }))
    if (!isCorrection) { update('orcid', ''); update('scopus_id', '') }
  }

  const verified = Boolean(status?.orcid)
  const shownOrcid = verified ? status.orcid : (isCorrection ? form.orcid : '')
  return (
    <div className="field field-span orcid-connect">
      <span>ORCID<b className="required"> *</b></span>
      {returnMessage && <Alert kind={returnMessage[0]}>{returnMessage[1]}</Alert>}
      {status && !status.configurado && <Alert kind="warning">El inicio de sesión con ORCID no está configurado en el servidor. Avise al coordinador.</Alert>}
      {shownOrcid ? (
        <p>
          <a href={`https://orcid.org/${shownOrcid}`} target="_blank" rel="noreferrer">{shownOrcid}</a>
          {verified && status.nombre && <> · {status.nombre}</>}
          {' '}<span className="small-muted">{verified ? 'Verificado con inicio de sesión en ORCID.' : 'Verificado al registrar la postulación.'}</span>
        </p>
      ) : <p className="muted">Inicia sesión en ORCID para comprobar que el identificador te pertenece.</p>}
      <div className="actions">
        <button type="button" className={`button ${shownOrcid ? 'button-outline' : 'button-primary'}`} disabled={!status?.configurado} onClick={connect}>
          {shownOrcid ? 'Conectar otra cuenta ORCID' : 'Conectar con ORCID'}
        </button>
        {verified && <button type="button" className="button button-quiet" onClick={disconnect}>Desconectar</button>}
      </div>
      <span>Scopus Author ID</span>
      <p>{form.scopus_id ? <a href={`https://www.scopus.com/authid/detail.uri?authorId=${form.scopus_id}`} target="_blank" rel="noreferrer">{form.scopus_id}</a> : <span className="muted">No encontrado en ORCID. Es opcional: el coordinador puede verificarlo manualmente.</span>}</p>
      <small>Se completa automáticamente si tu perfil de Scopus está vinculado a tu ORCID.</small>
    </div>
  )
}

function ApplicationForm({ initial = EMPTY_APPLICATION, onSubmit, isCorrection = false, submitLabel, children }) {
  const { request } = useAuth()
  const [form, setForm] = useState(() => ({ ...EMPTY_APPLICATION, ...initial, ...(readDraft(isCorrection ? 'investigator' : 'register') || {}) }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const update = useCallback((key, value) => setForm((current) => ({ ...current, [key]: value })), [])
  async function uploadPhoto(file) {
    if (!file) return
    if (file.size > FOTO_MAX_BYTES) { setError('La foto no puede superar los 2 MB.'); return }
    setUploading(true); setError('')
    try {
      const body = new FormData()
      body.append('file', file)
      const data = await request('/api/uploads/photo', { method: 'POST', body })
      update('foto', data.foto)
    } catch (problem) { setError(problem.message) } finally { setUploading(false) }
  }
  async function submit(event) {
    event.preventDefault(); setError('')
    if (!form.orcid) { setError('Conecta tu cuenta ORCID antes de enviar la postulación.'); return }
    setBusy(true)
    try {
      await onSubmit({
        ...form, codigo_ucsm: Number(form.codigo_ucsm), celular: String(form.celular),
        scopus_id: form.scopus_id ? Number(form.scopus_id) : null,
        intereses: Array.isArray(form.intereses) ? form.intereses : form.intereses.split(/[,\n;]/).map((value) => value.trim()).filter(Boolean),
      })
      clearDraft()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return (
    <form className="panel form-grid" onSubmit={submit}>
      {error && <Alert kind="error">{error}</Alert>}
      <h2 className="form-section-title">Identificación y cuenta</h2>
      <TextField label="DNI" name="dni" value={form.dni} onChange={(v) => update('dni', v.replace(/\D/g, ''))} required maxLength={8} />
      <TextField label="Código institucional" name="codigo_ucsm" value={form.codigo_ucsm} onChange={(v) => update('codigo_ucsm', v.replace(/\D/g, ''))} required />
      <TextField label="Correo electrónico" name="correo" type="email" value={form.correo} onChange={(v) => update('correo', v)} required />
      <TextField label="Nombres" name="nombres" value={form.nombres} onChange={(v) => update('nombres', v)} required maxLength={60} />
      <TextField label="Apellido paterno" name="apellido_paterno" value={form.apellido_paterno} onChange={(v) => update('apellido_paterno', v)} required maxLength={40} />
      <TextField label="Apellido materno" name="apellido_materno" value={form.apellido_materno} onChange={(v) => update('apellido_materno', v)} required maxLength={40} />
      <label className="field"><span>Género *</span><select value={form.genero} required onChange={(event) => update('genero', event.target.value)}><option>Femenino</option><option>Masculino</option></select></label>
      <TextField label="Fecha de nacimiento" name="fecha_nacimiento" type="date" value={String(form.fecha_nacimiento || '').slice(0, 10)} onChange={(v) => update('fecha_nacimiento', v)} required />
      <label className="field">
        <span>Escuela profesional<b className="required"> *</b></span>
        <select value={form.escuela} required onChange={(event) => update('escuela', event.target.value)}>
          <option value="" disabled>Seleccione una escuela…</option>
          {ESCUELAS.map((escuela) => <option key={escuela} value={escuela}>{escuela}</option>)}
        </select>
      </label>
      <TextField label="Celular" name="celular" type="tel" value={form.celular} onChange={(v) => update('celular', v.replace(/\D/g, ''))} required maxLength={9} help="Nueve dígitos, comienza con 9." />
      <h2 className="form-section-title">Información académica</h2>
      <OrcidConnectField form={form} update={update} isCorrection={isCorrection} />
      <TextField label="Enlace CTI Vitae" name="link_cti" type="url" value={form.link_cti} onChange={(v) => update('link_cti', v)} required />
      <label className="field">
        <span>Foto de perfil (.jpg/.png, máx. 2 MB)<b className="required"> *</b></span>
        <input
          name="foto" type="file" accept=".jpg,.jpeg,.png" required={!form.foto}
          onChange={(event) => uploadPhoto(event.target.files?.[0])}
        />
        {uploading && <small>Subiendo foto…</small>}
        {!uploading && form.foto && (
          <div className="photo-preview">
            <img src={form.foto} alt="Vista previa de la foto de perfil" />
            <small>Foto cargada correctamente.</small>
          </div>
        )}
      </label>
      <TextArea label="Resumen académico" value={form.resumen} onChange={(v) => update('resumen', v)} required rows={5} />
      <label className="field field-span"><span>Objetivos de Desarrollo Sostenible *</span><div className="ods-grid">{ODS.map((ods) => <label key={ods} className="check-option"><input type="checkbox" checked={form.ods.includes(ods)} onChange={(event) => update('ods', event.target.checked ? [...form.ods, ods] : form.ods.filter((value) => value !== ods))} />{ods}</label>)}</div></label>
      <TextArea label="Intereses de investigación (separados por coma)" value={Array.isArray(form.intereses) ? form.intereses.join(', ') : form.intereses} onChange={(v) => update('intereses', v)} required rows={3} />
      {isCorrection && <p className="notice field-span">Si el DNI o el código institucional estaban mal escritos, puede corregirlos aquí. El sistema verificará que no estén en uso por otra cuenta.</p>}
      {children}
      <div className="form-actions field-span"><button className="button button-primary" disabled={busy}>{busy ? 'Guardando…' : submitLabel}</button></div>
    </form>
  )
}

function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  if (user) return <Navigate to={homeFor(user.role)} replace />
  async function submit(application) {
    if (password.length < 12) throw new Error('La contraseña debe tener al menos 12 caracteres.')
    if (password !== confirmation) throw new Error('Las contraseñas no coinciden.')
    const result = await register({ application, password })
    navigate('/login/investigator', { state: { registered: true, email: result.correo } })
  }
  return (
    <div className="page-stack">
      <div className="page-heading"><p className="eyebrow">Nueva postulación</p><h1>Crear cuenta de investigador</h1><p>Completa tus datos. El coordinador revisará la solicitud y tomará la decisión.</p></div>
      <ApplicationForm onSubmit={submit} submitLabel="Enviar postulación">
        <h2 className="form-section-title">Seguridad de la cuenta</h2>
        <PasswordField label="Contraseña (mínimo 12 caracteres)" name="password" value={password} onChange={setPassword} required autoComplete="new-password" />
        <PasswordField label="Confirmar contraseña" name="password-confirm" value={confirmation} onChange={setConfirmation} required autoComplete="new-password" />
      </ApplicationForm>
    </div>
  )
}

function StatusBadge({ value }) {
  const labels = { pendiente_revision: 'Pendiente de revisión', observada: 'Observada', aprobada: 'Aprobada', rechazada: 'Rechazada' }
  return <span className={`status status-${value}`}>{labels[value] || value}</span>
}

function CoordinatorDashboard() {
  const { request } = useAuth()
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [today] = useState(() => {
    const date = new Date()
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  })
  const reload = useCallback(async () => {
    const [indicators, applications, patents, pure] = await Promise.all([
      request('/api/coordinator/dashboard'),
      request('/api/coordinator/applications'),
      request('/api/coordinator/patents'),
      request('/api/coordinator/pure-pending'),
    ])
    setSummary({
      indicators,
      applications: applications.length,
      patents: patents.length,
      pure: pure.length,
    })
  }, [request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  async function generateReport() {
    setError(''); setMessage(''); setBusy(true)
    try {
      await request('/api/coordinator/reports/issued', { method: 'POST', body: { fecha: today } })
      setMessage(`Reporte del ${today} generado correctamente.`)
      await reload()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  const indicators = summary?.indicators
  const cards = [
    ['Investigadores', indicators?.investigadores, BsPeople],
    ['Escuelas profesionales', indicators?.escuelas, BsBuildings],
    ['Publicaciones', indicators?.publicaciones, BsClockHistory],
    ['Patentes', indicators?.patentes, BsAward],
    ['ODS vinculados', indicators?.ods_vinculados, BsClipboard2Check],
  ]
  const maxOds = Math.max(1, ...(indicators?.ranking_ods || []).map(([, total]) => total))
  return (
    <div className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Panel de gestión institucional</p>
        <h1>Inicio del coordinador</h1>
        <p>Indicadores actuales del repositorio y accesos a las tareas pendientes.</p>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="kpi-grid">
        {cards.map(([label, value, Icon]) => <article className="kpi-card" key={label}>
          <span className="kpi-icon"><Icon aria-hidden="true" /></span>
          <strong>{value ?? '—'}</strong>
          <span>{label}</span>
        </article>)}
      </div>
      <div className="dashboard-panels">
        <section className="panel"><h2>Ranking de ODS vinculados</h2>
          {indicators?.ranking_ods?.length ? <div className="rank-list">{indicators.ranking_ods.map(([ods, total]) => <div className="rank-row" key={ods}>
            <span>{ods}</span><span className="rank-track"><i style={{ width: `${Math.max(4, total / maxOds * 100)}%` }} /></span><strong>{total}</strong>
          </div>)}</div> : <p className="muted">Aún no hay ODS registrados.</p>}
        </section>
        <section className="panel"><h2>Escuelas con más investigadores</h2>
          {indicators?.top_escuelas?.length ? <ol className="school-rank">{indicators.top_escuelas.map(([school, total]) => <li key={school}>
            <span>{school}</span><strong>{total}</strong>
          </li>)}</ol> : <p className="muted">Aún no hay investigadores registrados.</p>}
        </section>
      </div>
      <section className="panel">
        <div className="section-title-row"><div><p className="eyebrow">Pendientes</p><h2>Procesos de revisión</h2></div><Link className="text-link" to="/coordinator/applications">Abrir bandeja completa</Link></div>
        <div className="queue-summary-grid">
          <Link className="queue-card" to="/coordinator/applications?tab=applications"><span>Postulaciones</span><strong>{summary?.applications ?? '—'}</strong><b>Revisar →</b></Link>
          <Link className="queue-card" to="/coordinator/applications?tab=patents"><span>Solicitudes de patente</span><strong>{summary?.patents ?? '—'}</strong><b>Revisar →</b></Link>
          <Link className="queue-card" to="/coordinator/applications?tab=pure"><span>Altas manuales en Pure</span><strong>{summary?.pure ?? '—'}</strong><b>Gestionar →</b></Link>
        </div>
      </section>
      <section className="panel quick-report">
        <div><p className="eyebrow">Acción rápida</p><h2>Reporte diario</h2><p className="muted">Genera el corte de indicadores para hoy ({today}).</p></div>
        <button className="button button-primary" disabled={busy} onClick={generateReport}>{busy ? 'Generando…' : 'Generar reporte de hoy'}</button>
      </section>
      {message && <Alert>{message}</Alert>}
      <p className="notice">Las consultas de identificadores son evidencia para la revisión; la aprobación siempre corresponde al coordinador.</p>
    </div>
  )
}

// --- Borrado lógico: filtro de estado y acciones de baja/reactivación ---------
const ESTADOS_REGISTRO = [['activos', 'Activos'], ['bajas', 'Dados de baja'], ['todos', 'Todos']]

function EstadoFilter({ value, onChange }) {
  return <label className="field estado-filter"><span>Mostrar</span><select value={value} onChange={(event) => onChange(event.target.value)}>{ESTADOS_REGISTRO.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
}

function EstadoBadge({ activo }) {
  return activo === false ? <span className="status status-rechazada">Dado de baja</span> : null
}

function BajaPanel({ entidad, registro, basePath, onChanged }) {
  const { request } = useAuth()
  const [motivo, setMotivo] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!registro) return null
  async function darDeBaja() {
    if (!window.confirm(`¿Dar de baja ${entidad}? El registro no se borra: queda inactivo y se puede reactivar.`)) return
    setBusy(true); setError('')
    try { await request(`${basePath}/baja`, { method: 'POST', body: { motivo: motivo.trim() || null } }); setMotivo(''); await onChanged(`Se dio de baja ${entidad}.`) }
    catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function reactivar() {
    setBusy(true); setError('')
    try { await request(`${basePath}/reactivar`, { method: 'POST', body: {} }); await onChanged(`Se reactivó ${entidad}.`) }
    catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return <div className="baja-panel">
    {error && <Alert kind="error">{error}</Alert>}
    {registro.activo === false ? <>
      <Alert kind="warning">Dado de baja el {String(registro.fecha_baja || '').slice(0, 16).replace('T', ' ')}{registro.motivo_baja ? ` · Motivo: ${registro.motivo_baja}` : ''}</Alert>
      <button type="button" className="button button-outline" disabled={busy} onClick={reactivar}>{busy ? 'Procesando…' : 'Reactivar'}</button>
    </> : <>
      <TextArea label="Motivo de la baja (opcional)" value={motivo} onChange={setMotivo} rows={2} maxLength={255} />
      <button type="button" className="button button-danger" disabled={busy} onClick={darDeBaja}>{busy ? 'Procesando…' : 'Dar de baja'}</button>
      <p className="small-muted">Borrado lógico: el registro deja de mostrarse en los listados y reportes, pero se conserva en la base de datos.</p>
    </>}
  </div>
}

function CoordinatorInvestigators() {
  const { request } = useAuth()
  const [term, setTerm] = useState('')
  const [search, setSearch] = useState('')
  const [estado, setEstado] = useState('activos')
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setError(''); setLoading(true)
    try { setItems(await request(`/api/coordinator/investigators?search=${encodeURIComponent(search)}&estado=${estado}`)) }
    catch (problem) { setError(problem.message) } finally { setLoading(false) }
  }, [request, search, estado])
  useEffect(() => { load() }, [load])
  async function open(code) {
    setError(''); setMessage(''); setSelected(code); setDetail(null)
    try { setDetail(await request(`/api/coordinator/investigators/${code}`)) }
    catch (problem) { setError(problem.message) }
  }
  async function changed(text) {
    setMessage(text); await load()
    setDetail(await request(`/api/coordinator/investigators/${selected}`))
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Directorio institucional</p><h1>Investigadores</h1><p>Consulta los perfiles aprobados y gestiona sus bajas. Las nuevas altas y correcciones se resuelven desde la Bandeja de revisión.</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    {message && <Alert kind="success">{message}</Alert>}
    <section className="panel">
      <form className="search-bar" onSubmit={(event) => { event.preventDefault(); setSearch(term) }}>
        <TextField label="Buscar por nombre o código institucional" value={term} onChange={setTerm} />
        <EstadoFilter value={estado} onChange={setEstado} />
        <button className="button button-primary"><BsSearch aria-hidden="true" />Buscar</button>
      </form>
      <div className="table-scroll"><table><thead><tr><th>Código institucional</th><th>Investigador</th><th>Escuela</th><th>Correo</th><th>Estado</th><th></th></tr></thead><tbody>
        {items.map((item) => <tr key={item.codigo_ucsm}><td>{item.codigo_ucsm}</td><td>{item.nombre}</td><td>{item.escuela}</td><td>{item.correo}</td><td>{item.activo ? 'Activo' : <EstadoBadge activo={false} />}</td><td><button className="text-link action-link" onClick={() => open(item.codigo_ucsm)}>Ver perfil</button></td></tr>)}
      </tbody></table></div>
      {loading && <p className="loading">Cargando investigadores…</p>}
      {!loading && !items.length && <div className="empty-state">No se encontraron investigadores.</div>}
    </section>
    {selected && <section className="panel">
      <div className="profile-heading">
        <h2>Perfil del investigador</h2>
        {detail?.foto && <img className="profile-photo" src={detail.foto} alt={`Foto de ${detail.nombres}`} />}
      </div>
      {!detail ? <p className="muted">Cargando perfil…</p> : <dl className="details-grid">
        {[
          ['Código institucional', detail.codigo_ucsm], ['Nombre', `${detail.nombres} ${detail.apellido_paterno} ${detail.apellido_materno}`],
          ['DNI', detail.dni], ['Escuela profesional', detail.escuela], ['Correo', detail.correo], ['Celular', detail.celular],
          ['Género', detail.genero], ['Fecha de nacimiento', String(detail.fecha_nacimiento || '').slice(0, 10)],
          ['ORCID', <a key="orcid-link" href={`https://orcid.org/${detail.orcid}`} target="_blank" rel="noreferrer">{detail.orcid}</a>],
          ['Scopus Author ID', detail.scopus_id || 'No registrado'], ['CTI Vitae', <a key="cti-link" href={detail.link_cti} target="_blank" rel="noreferrer">{detail.link_cti}</a>],
          ['Estado en Pure', detail.pure_estado === 'registrado_manual' ? `Registrado · ${detail.pure_person_id}` : 'Pendiente de registro manual'],
          ['ODS', detail.ods?.join(', ') || '—'], ['Intereses', detail.intereses || '—'], ['Resumen', detail.resumen || '—'],
        ].map(([label, value]) => <div className="detail-pair" key={label}><dt>{label}</dt><dd>{value || '—'}</dd></div>)}
      </dl>}
      <BajaPanel entidad="al investigador" registro={detail} basePath={`/api/coordinator/investigators/${selected}`} onChanged={changed} />
    </section>}
  </div>
}

function CoordinatorPatentRegistry() {
  const { request } = useAuth()
  const [items, setItems] = useState([])
  const [estado, setEstado] = useState('activos')
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    setError(''); setLoading(true)
    try { setItems(await request(`/api/coordinator/patent-registry?estado=${estado}`)) }
    catch (problem) { setError(problem.message) } finally { setLoading(false) }
  }, [request, estado])
  useEffect(() => { load() }, [load])
  async function open(number) {
    setError(''); setMessage(''); setSelected(number); setDetail(null)
    try { setDetail(await request(`/api/coordinator/patent-registry/${encodeURIComponent(number)}`)) }
    catch (problem) { setError(problem.message) }
  }
  async function changed(text) {
    setMessage(text); await load()
    setDetail(await request(`/api/coordinator/patent-registry/${encodeURIComponent(selected)}`))
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Propiedad intelectual</p><h1>Patentes registradas</h1><p>Consulta el catálogo definitivo y gestiona sus bajas. Las nuevas patentes se incorporan al aprobar una solicitud en la Bandeja.</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    {message && <Alert kind="success">{message}</Alert>}
    <section className="panel">
      <div className="search-bar"><EstadoFilter value={estado} onChange={setEstado} /></div>
      <div className="table-scroll"><table><thead><tr><th>Número</th><th>Título</th><th>Fecha de registro</th><th>País</th><th>Inventores</th><th>Estado</th><th></th></tr></thead><tbody>
        {items.map((item) => <tr key={item.n_patente}><td>{item.n_patente}</td><td>{item.titulo}</td><td>{String(item.fecha_registro).slice(0, 10)}</td><td>{item.pais}</td><td>{item.inventores || '—'}</td><td>{item.activo ? 'Activa' : <EstadoBadge activo={false} />}</td><td><button className="text-link action-link" onClick={() => open(item.n_patente)}>Ver detalle</button></td></tr>)}
      </tbody></table></div>
      {loading && <p className="loading">Cargando patentes…</p>}
      {!loading && !items.length && <div className="empty-state">No hay patentes registradas.</div>}
    </section>
    {selected && <section className="panel">
      <h2>Detalle de patente · {selected}</h2>
      {!detail ? <p className="muted">Cargando detalle…</p> : <dl className="details-grid">
        {[
          ['Título', detail.titulo], ['Entidad registradora', detail.editorial], ['Fecha de registro', String(detail.fecha_registro).slice(0, 10)],
          ['País', detail.pais], ['Clasificación CIP', detail.cip], ['Inventores', detail.inventores?.join(', ')],
          ['Clasificación OCDE', detail.ocde || '—'],
        ].map(([label, value]) => <div className="detail-pair" key={label}><dt>{label}</dt><dd>{value || '—'}</dd></div>)}
      </dl>}
      <BajaPanel entidad="la patente" registro={detail} basePath={`/api/coordinator/patent-registry/${encodeURIComponent(selected)}`} onChanged={changed} />
    </section>}
  </div>
}

// --- Histórico: seguimiento del uso de repositorios (Tarea 2) ---------------
// Resumen del repositorio, uso de suscripciones de biblioteca (COUNTER 5) e
// importación de reportes. Los datos de uso son agregados por plataforma y
// mes: no hay información por estudiante.
const USO_METRICAS = [
  ['Total_Item_Requests', 'Descargas y vistas de texto completo'],
  ['Unique_Item_Requests', 'Documentos únicos consultados'],
  ['Total_Item_Investigations', 'Interacciones totales (resúmenes, vistas, descargas)'],
  ['Searches_Platform', 'Búsquedas realizadas'],
]
const USO_COLORES = ['#06402b', '#2f8f5b', '#c08a1e', '#3b6fb6', '#8a4fa3', '#b6463b']
const formatoNumero = (valor) => Number(valor || 0).toLocaleString('es-PE')

function BarList({ items, label, value }) {
  const max = Math.max(1, ...items.map((item) => Number(item[value])))
  if (!items.length) return <p className="muted">Sin datos todavía.</p>
  return <ul className="bar-list">{items.map((item) => <li key={item[label]}>
    <span className="bar-list-label">{item[label]}</span>
    <span className="bar-list-track"><span style={{ width: `${(Number(item[value]) / max) * 100}%` }} /></span>
    <strong>{formatoNumero(item[value])}</strong>
  </li>)}</ul>
}

function RepositorySummary({ onGo }) {
  const { request } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { request('/api/coordinator/repository/summary').then(setData).catch((problem) => setError(problem.message)) }, [request])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <div className="loading">Cargando resumen…</div>
  const sync = data.ultima_sincronizacion ? new Date(data.ultima_sincronizacion).toLocaleDateString('es-PE') : '—'
  return <div className="page-stack">
    <div className="kpi-grid">
      <article className="kpi-card"><span className="kpi-icon"><BsClockHistory aria-hidden="true" /></span><strong>{formatoNumero(data.publicaciones)}</strong><span>Publicaciones en el repositorio</span></article>
      <article className="kpi-card"><span className="kpi-icon"><BsBuildings aria-hidden="true" /></span><strong>{formatoNumero(data.tipos)}</strong><span>Tipos de publicación</span></article>
      <article className="kpi-card"><span className="kpi-icon"><BsSearch aria-hidden="true" /></span><strong>{formatoNumero(data.uso_total_ultimos_12_meses)}</strong><span>Descargas en suscripciones (12 meses)</span></article>
      <article className="kpi-card"><span className="kpi-icon"><BsFileEarmarkBarGraph aria-hidden="true" /></span><strong>{sync}</strong><span>Última sincronización con Pure</span></article>
    </div>
    <div className="summary-grid">
      <section className="panel"><h2>Publicaciones por año</h2><BarList items={data.por_anio} label="anio" value="total" /></section>
      <section className="panel"><h2>Por tipo</h2><BarList items={data.por_tipo} label="tipo" value="total" /></section>
      <section className="panel"><h2>Por escuela profesional</h2><BarList items={data.por_escuela} label="escuela" value="total" /></section>
      <section className="panel"><h2>Por ODS</h2><BarList items={data.por_ods} label="ods" value="total" /></section>
      <section className="panel"><div className="section-title-row"><h2>Plataformas más usadas</h2><button type="button" className="text-link" onClick={() => onGo('uso')}>Ver detalle</button></div><BarList items={data.uso_ultimos_12_meses} label="plataforma" value="total" /></section>
      <section className="panel"><h2>Reportes</h2><p className="muted">Los reportes del coordinador se generan a partir de este histórico.</p><Link className="button button-primary" to="/coordinator/reports">Generar reporte</Link></section>
    </div>
  </div>
}

function UsageChart({ serie }) {
  const plataformas = serie.totales.map((item) => item.plataforma)
  const periodos = serie.periodos
  if (!periodos.length) return <div className="empty-state">No hay datos de uso para los filtros elegidos.</div>
  const valor = {}
  serie.filas.forEach((fila) => { valor[`${fila.plataforma}|${fila.periodo}`] = fila.valor })
  const max = Math.max(1, ...serie.filas.map((fila) => fila.valor))
  const ancho = 760, alto = 260, margen = { izq: 56, der: 12, sup: 12, inf: 36 }
  const x = (i) => margen.izq + (periodos.length === 1 ? 0 : (i / (periodos.length - 1)) * (ancho - margen.izq - margen.der))
  const y = (v) => alto - margen.inf - (v / max) * (alto - margen.sup - margen.inf)
  const marcas = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f))
  return <figure className="usage-chart">
    <svg viewBox={`0 0 ${ancho} ${alto}`} role="img" aria-label="Uso mensual por plataforma">
      {marcas.map((m) => <g key={m}><line x1={margen.izq} x2={ancho - margen.der} y1={y(m)} y2={y(m)} className="chart-grid" /><text x={margen.izq - 6} y={y(m) + 4} textAnchor="end" className="chart-axis">{formatoNumero(m)}</text></g>)}
      {periodos.map((p, i) => (periodos.length <= 12 || i % Math.ceil(periodos.length / 12) === 0) && <text key={p} x={x(i)} y={alto - 12} textAnchor="middle" className="chart-axis">{p}</text>)}
      {plataformas.map((plataforma, k) => {
        const puntos = periodos.map((p, i) => [x(i), y(valor[`${plataforma}|${p}`] || 0)])
        return <g key={plataforma}>
          <polyline fill="none" stroke={USO_COLORES[k % USO_COLORES.length]} strokeWidth="2.5" points={puntos.map((pt) => pt.join(',')).join(' ')} />
          {puntos.map(([px, py], i) => <circle key={i} cx={px} cy={py} r="3" fill={USO_COLORES[k % USO_COLORES.length]}><title>{`${plataforma} · ${periodos[i]}: ${formatoNumero(valor[`${plataforma}|${periodos[i]}`] || 0)}`}</title></circle>)}
        </g>
      })}
    </svg>
    <figcaption className="chart-legend">{plataformas.map((plataforma, k) => <span key={plataforma}><i style={{ background: USO_COLORES[k % USO_COLORES.length] }} />{plataforma}</span>)}</figcaption>
  </figure>
}

function UsagePanel({ onGo }) {
  const { request } = useAuth()
  const [options, setOptions] = useState(null)
  const [filtros, setFiltros] = useState({ metrica: 'Total_Item_Requests', plataformas: [], desde: '', hasta: '' })
  const [serie, setSerie] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    request('/api/coordinator/usage/options').then((data) => {
      setOptions(data)
      setFiltros((actual) => ({ ...actual, desde: data.desde ? data.desde.slice(0, 7) : '', hasta: data.hasta ? data.hasta.slice(0, 7) : '' }))
    }).catch((problem) => setError(problem.message))
  }, [request])
  const query = useMemo(() => {
    const params = new URLSearchParams({ metrica: filtros.metrica })
    filtros.plataformas.forEach((p) => params.append('plataforma', p))
    if (filtros.desde) params.set('desde', filtros.desde)
    if (filtros.hasta) params.set('hasta', filtros.hasta)
    return params
  }, [filtros])
  useEffect(() => {
    if (!options) return
    request(`/api/coordinator/usage?${query}`).then((data) => { setSerie(data); setError('') }).catch((problem) => setError(problem.message))
  }, [request, options, query])
  if (error && !options) return <Alert kind="error">{error}</Alert>
  if (!options) return <div className="loading">Cargando uso de suscripciones…</div>
  if (!options.plataformas.length) return <section className="panel empty-state">Aún no hay datos de uso. <button type="button" className="text-link" onClick={() => onGo('importar')}>Importe un reporte COUNTER</button> para empezar.</section>
  const exportar = new URLSearchParams(query); exportar.delete('metrica')
  const tabla = serie ? serie.periodos.map((periodo) => ({ periodo, valores: Object.fromEntries(serie.filas.filter((f) => f.periodo === periodo).map((f) => [f.plataforma, f.valor])) })) : []
  const plataformas = serie ? serie.totales.map((t) => t.plataforma) : []
  return <div className="page-stack">
    {error && <Alert kind="error">{error}</Alert>}
    <section className="panel">
      <h2>Uso de las suscripciones de biblioteca</h2>
      <p className="muted">Uso mensual de las bases de datos suscritas por la universidad, según los reportes COUNTER de cada editor.</p>
      <div className="usage-filters">
        <label className="field"><span>Indicador</span><select value={filtros.metrica} onChange={(event) => setFiltros({ ...filtros, metrica: event.target.value })}>{USO_METRICAS.filter(([key]) => options.metricas.includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label className="field"><span>Desde</span><input type="month" value={filtros.desde} onChange={(event) => setFiltros({ ...filtros, desde: event.target.value })} /></label>
        <label className="field"><span>Hasta</span><input type="month" value={filtros.hasta} onChange={(event) => setFiltros({ ...filtros, hasta: event.target.value })} /></label>
        <a className="button button-outline" href={`/api/coordinator/usage/export.csv?${exportar}`}>Exportar CSV</a>
      </div>
      <div className="platform-filter">{options.plataformas.map((p) => <label key={p} className="check-option"><input type="checkbox" checked={!filtros.plataformas.length || filtros.plataformas.includes(p)} onChange={(event) => {
        const actuales = filtros.plataformas.length ? filtros.plataformas : options.plataformas
        const siguiente = event.target.checked ? [...actuales, p] : actuales.filter((x) => x !== p)
        setFiltros({ ...filtros, plataformas: siguiente.length === options.plataformas.length ? [] : siguiente })
      }} />{p}</label>)}</div>
      {serie && <UsageChart serie={serie} />}
    </section>
    {serie && serie.periodos.length > 0 && <section className="panel">
      <h2>Detalle por mes</h2>
      <div className="table-scroll"><table>
        <thead><tr><th>Mes</th>{plataformas.map((p) => <th key={p}>{p}</th>)}</tr></thead>
        <tbody>{tabla.map((fila) => <tr key={fila.periodo}><td>{fila.periodo}</td>{plataformas.map((p) => <td key={p}>{formatoNumero(fila.valores[p])}</td>)}</tr>)}</tbody>
        <tfoot><tr><th>Total</th>{serie.totales.map((t) => <th key={t.plataforma}>{formatoNumero(t.total)}</th>)}</tr></tfoot>
      </table></div>
    </section>}
  </div>
}

function UsageImport({ onImported }) {
  const { request } = useAuth()
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [imports, setImports] = useState([])
  const [sushiActivo, setSushiActivo] = useState(false)
  const [rango, setRango] = useState({ desde: '', hasta: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const loadImports = useCallback(() => request('/api/coordinator/usage/imports').then(setImports).catch(() => {}), [request])
  useEffect(() => {
    loadImports()
    request('/api/coordinator/usage/options').then((data) => setSushiActivo(data.sushi_activo)).catch(() => {})
  }, [request, loadImports])
  async function send(path) {
    const body = new FormData(); body.append('file', file)
    return request(path, { method: 'POST', body })
  }
  async function previsualizar() {
    setBusy(true); setError(''); setMessage(''); setPreview(null)
    try { setPreview(await send('/api/coordinator/usage/import/preview')) } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function importar() {
    setBusy(true); setError('')
    try {
      const result = await send('/api/coordinator/usage/import')
      setMessage(`Reporte importado: ${result.creados} registros nuevos y ${result.actualizados} actualizados.`)
      setPreview(null); setFile(null); await loadImports(); onImported?.()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function sincronizar() {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await request('/api/coordinator/usage/sushi-sync', { method: 'POST', body: rango })
      setMessage(`Descarga SUSHI completada: ${result.creados} nuevos y ${result.actualizados} actualizados.`)
      await loadImports(); onImported?.()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return <section className="panel">
    <h2>Reporte de uso de suscripciones (COUNTER 5)</h2>
    <p className="muted">Descargue el reporte de plataforma (PR) del portal de administración del editor (por ejemplo, Elsevier) y súbalo aquí en formato JSON o CSV. Primero se muestra una vista previa; nada se guarda hasta confirmar. Volver a subir un mes ya cargado actualiza sus valores.</p>
    {error && <Alert kind="error">{error}</Alert>}
    {message && <Alert kind="success">{message}</Alert>}
    <div className="usage-filters">
      <label className="field"><span>Archivo COUNTER</span><input type="file" accept=".json,.csv,.tsv,.txt" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null) }} /></label>
      <button type="button" className="button button-outline" disabled={!file || busy} onClick={previsualizar}>{busy && !preview ? 'Leyendo…' : 'Vista previa'}</button>
    </div>
    {preview && <div className="import-preview">
      <dl className="details-grid">
        <dt>Plataformas</dt><dd>{preview.plataformas.join(', ')}</dd>
        <dt>Periodo</dt><dd>{preview.desde.slice(0, 7)} a {preview.hasta.slice(0, 7)}</dd>
        <dt>Indicadores</dt><dd>{preview.metricas.join(', ')}</dd>
        <dt>Registros</dt><dd>{preview.filas}</dd>
        {preview.metricas_ignoradas.length > 0 && <><dt>Ignorados</dt><dd>{preview.metricas_ignoradas.join(', ')}</dd></>}
      </dl>
      <div className="form-actions"><button type="button" className="button button-primary" disabled={busy} onClick={importar}>{busy ? 'Importando…' : 'Confirmar importación'}</button><button type="button" className="button button-quiet" onClick={() => setPreview(null)}>Cancelar</button></div>
    </div>}
    <h3>Descarga automática (SUSHI)</h3>
    {sushiActivo ? <div className="usage-filters">
      <label className="field"><span>Desde</span><input type="month" value={rango.desde} onChange={(event) => setRango({ ...rango, desde: event.target.value })} /></label>
      <label className="field"><span>Hasta</span><input type="month" value={rango.hasta} onChange={(event) => setRango({ ...rango, hasta: event.target.value })} /></label>
      <button type="button" className="button button-outline" disabled={busy || !rango.desde || !rango.hasta} onClick={sincronizar}>Descargar del editor</button>
    </div> : <p className="notice">No está activada: requiere las credenciales COUNTER de la biblioteca (sección [sushi] de config.ini). Mientras tanto, importe los reportes como archivo.</p>}
    <h3>Últimas importaciones</h3>
    {imports.length ? <div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Origen</th><th>Archivo</th><th>Nuevos</th><th>Actualizados</th></tr></thead>
      <tbody>{imports.map((item) => <tr key={item.id}><td>{new Date(item.iniciada_en).toLocaleString('es-PE')}</td><td>{item.sistema === 'sushi' ? 'SUSHI' : 'Archivo'}</td><td>{item.archivo || '—'}</td><td>{item.registros_creados}</td><td>{item.registros_actualizados}</td></tr>)}</tbody></table></div>
      : <p className="muted">Todavía no se importaron reportes.</p>}
  </section>
}

function CoordinatorPublications() {
  const { request } = useAuth()
  const [term, setTerm] = useState('')
  const [search, setSearch] = useState('')
  const [estado, setEstado] = useState('activos')
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = ['resumen', 'catalog', 'uso', 'importar'].includes(searchParams.get('pestana')) ? searchParams.get('pestana') : 'resumen'
  const setTab = useCallback((value) => setSearchParams({ pestana: value }), [setSearchParams])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    setError('')
    try {
      setItems(await request(`/api/coordinator/publications?search=${encodeURIComponent(search)}&estado=${estado}`))
    } catch (problem) { setError(problem.message) } finally { setLoading(false) }
  }, [request, search, estado])
  useEffect(() => { load() }, [load])
  async function select(uuid) {
    setError(''); setMessage(''); setSelected(null)
    try {
      setSelected(await request(`/api/coordinator/publications/${uuid}`))
    } catch (problem) { setError(problem.message) }
  }
  async function changed(text) {
    setMessage(text); await load()
    setSelected(await request(`/api/coordinator/publications/${selected.uuid}`))
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Seguimiento del uso de repositorios</p><h1>Histórico</h1><p>Lo que contiene el repositorio institucional, cuánto se usan las suscripciones de biblioteca y la fuente de los reportes del coordinador.</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    {message && <Alert kind="success">{message}</Alert>}
    <div className="tab-row" role="tablist">
      {[['resumen', 'Resumen'], ['catalog', 'Publicaciones'], ['uso', 'Uso de suscripciones'], ['importar', 'Importar datos']].map(([key, label]) => <button key={key} className={`tab-button${tab === key ? ' selected' : ''}`} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {tab === 'resumen' && <RepositorySummary onGo={setTab} />}
    {tab === 'uso' && <UsagePanel onGo={setTab} />}
    {tab === 'importar' && <div className="page-stack"><UsageImport /><section className="panel"><h2>Publicaciones desde Pure</h2><PureImportReview /></section></div>}
    {tab === 'catalog' && <div className="publication-layout">
      <section className="panel publication-list">
        <h2>Catálogo oficial</h2>
        <form className="search-bar" onSubmit={(event) => { event.preventDefault(); setSearch(term) }}>
          <TextField label="Buscar por título" value={term} onChange={setTerm} />
          <EstadoFilter value={estado} onChange={setEstado} />
          <button className="button button-primary"><BsSearch aria-hidden="true" />Buscar</button>
        </form>
        <div className="publication-results">{items.map((item) => <button className={`publication-result${selected?.uuid === item.uuid ? ' selected' : ''}`} key={item.uuid} onClick={() => select(item.uuid)}>
          <strong>{item.titulo}</strong><span>{item.anio} · {item.tipo}</span><small>{item.idioma} · {item.categoria}</small>{!item.activo && <EstadoBadge activo={false} />}
        </button>)}</div>
        {loading && <p className="loading">Cargando publicaciones…</p>}
        {!loading && !items.length && <div className="empty-state">No se encontraron publicaciones.</div>}
      </section>
      <section className="panel">
        <h2>Detalle de publicación</h2>
        {!selected ? <p className="muted">Selecciona una publicación para consultar sus datos.</p> : <dl className="details-grid">
          {Object.entries(selected.formulario).map(([label, value]) => <div className="detail-pair" key={label}><dt>{label.replaceAll('_', ' ')}</dt><dd>{value || '—'}</dd></div>)}
          <div className="detail-pair"><dt>UUID</dt><dd>{selected.uuid}</dd></div>
        </dl>}
        <BajaPanel entidad="la publicación" registro={selected} basePath={selected ? `/api/coordinator/publications/${selected.uuid}` : ''} onChanged={changed} />
      </section>
    </div>}
  </div>
}

function candidateFormValues(values) {
  const volume = String(values.volumen ?? '')
  const journalNumber = String(values.journal_number ?? '')
  const bibliographicalNote = String(values.bibliographical_note ?? '')
  return {
    title: values.title || '',
    publication_year: String(values.publication_year ?? ''),
    type: values.type || '',
    peer_review: typeof values.peer_review === 'boolean'
      ? String(values.peer_review)
      : ['true', 'false'].includes(String(values.peer_review).toLowerCase())
        ? String(values.peer_review).toLowerCase()
        : '',
    language: values.language || '',
    category: values.category || '',
    portal_url: values.portal_url || '',
    abstract: values.abstract || '',
    volumen: /^\d+$/.test(volume) && Number(volume) > 0 ? volume : '',
    number_of_pages: String(values.number_of_pages ?? ''),
    pages: values.pages || '',
    journal_number: journalNumber.length <= 10 ? journalNumber : '',
    bibliographical_note: bibliographicalNote.length <= 500 ? bibliographicalNote : '',
    publication_status: (values.publication_status || []).join('\n'),
    links: values.links || [],
    contributors: (values.contributors || []).join('\n'),
    identifiers: (values.identifiers || []).join('\n'),
    keywords_groups: (values.keywords_groups || []).join('\n'),
  }
}

function splitList(value) {
  return value.split(/[;\n]+/).map((item) => item.trim()).filter(Boolean)
}

function PureImportReview() {
  const { request } = useAuth()
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [importSummary, setImportSummary] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [candidates, setCandidates] = useState({ items: [], total: 0 })
  const [candidate, setCandidate] = useState(null)
  const [curation, setCuration] = useState(null)
  const [researcherTerm, setResearcherTerm] = useState('')
  const [researchers, setResearchers] = useState([])
  const [reason, setReason] = useState('')
  const [discardReason, setDiscardReason] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const sourceVolume = candidate?.metadatos_origen?.data?.volume
  const sourceVolumeIsNumeric = sourceVolume == null
    || (/^\d+$/.test(String(sourceVolume)) && Number(sourceVolume) > 0)
  const loadCandidates = useCallback(async () => {
    try {
      const result = await request(
        `/api/coordinator/publications/candidates?search=${encodeURIComponent(search)}&limit=50&offset=${page * 50}`,
      )
      setCandidates(result)
      setError('')
    } catch (problem) { setError(problem.message) }
  }, [page, request, search])
  useEffect(() => { loadCandidates() }, [loadCandidates])

  function fileChanged(value) {
    setFile(value)
    setPreview(null); setImportSummary(null); setMessage(''); setError('')
  }
  function uploadBody() {
    const body = new FormData()
    body.append('file', file)
    return body
  }
  async function previewFile() {
    if (!file) return
    setError(''); setMessage(''); setBusy(true); setPreview(null)
    try {
      setPreview(await request('/api/coordinator/publications/import/preview', {
        method: 'POST', body: uploadBody(),
      }))
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function importFile() {
    if (!file || !preview?.validas) return
    if (!window.confirm(`Se guardarán ${preview.validas} filas válidas como candidaturas pendientes. Ninguna se publicará todavía en Histórico. ¿Continuar?`)) return
    setError(''); setMessage(''); setBusy(true)
    try {
      const result = await request('/api/coordinator/publications/import', {
        method: 'POST', body: uploadBody(),
      })
      setImportSummary(result)
      const automatic = result.consolidacion_automatica
      setMessage(automatic
        ? `Importación procesada: ${automatic.publicaciones_consolidadas} publicaciones se consolidaron automáticamente; ${automatic.revision_manual} quedan pendientes de revisión.`
        : 'No hubo candidaturas nuevas para procesar. Revisa el resumen de importación.')
      setPage(0)
      await loadCandidates()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function openCandidate(id) {
    setError(''); setCandidate(null); setCuration(null); setReason(''); setDiscardReason('')
    try {
      const detail = await request(`/api/coordinator/publications/candidates/${id}`)
      setCandidate(detail); setCuration(candidateFormValues(detail.curacion))
    } catch (problem) { setError(problem.message) }
  }
  function updateCuration(key, value) {
    setCuration((current) => ({ ...current, [key]: value }))
  }
  function updateSourceLink(index, key, value) {
    setCuration((current) => ({
      ...current,
      links: current.links.map((link, itemIndex) => (
        itemIndex === index ? { ...link, [key]: value } : link
      )),
    }))
  }
  async function saveCuration(event) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true)
    const body = {
      title: curation.title,
      publication_year: Number(curation.publication_year),
      type: curation.type,
      peer_review: curation.peer_review === 'true',
      language: curation.language,
      category: curation.category,
      portal_url: curation.portal_url,
      abstract: curation.abstract || null,
      volumen: curation.volumen ? Number(curation.volumen) : null,
      number_of_pages: curation.number_of_pages ? Number(curation.number_of_pages) : null,
      journal_number: curation.journal_number || null,
      bibliographical_note: curation.bibliographical_note || null,
      publication_status: splitList(curation.publication_status),
      links: curation.links.map((link) => ({
        pure_id: Number(link.pure_id),
        link_type: link.link_type,
        url: link.url,
        description: link.description || null,
      })),
      pages: curation.pages || null,
      contributors: splitList(curation.contributors),
      identifiers: splitList(curation.identifiers),
      keywords_groups: splitList(curation.keywords_groups),
    }
    try {
      const result = await request(`/api/coordinator/publications/candidates/${candidate.id}/curation`, { method: 'PUT', body })
      const automatic = result.consolidacion_automatica
      setMessage(automatic
        ? `Depuración guardada. Se consolidaron automáticamente ${automatic.publicaciones_consolidadas} publicaciones del lote; ${automatic.revision_manual} siguen pendientes.`
        : 'Depuración guardada en la candidatura. El Histórico oficial no cambió porque este registro no pertenece a un lote Pure procesable.')
      await openCandidate(candidate.id)
      await loadCandidates()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function findResearchers(event) {
    event.preventDefault(); setError('')
    try {
      setResearchers(await request(`/api/coordinator/investigators?search=${encodeURIComponent(researcherTerm)}`))
    } catch (problem) { setError(problem.message) }
  }
  async function discardCandidate() {
    if (!discardReason.trim()) {
      setError('Indica el motivo para descartar la candidatura.')
      return
    }
    if (!window.confirm('La candidatura dejará de aparecer en la lista de pendientes. ¿Descartarla?')) return
    setError(''); setMessage(''); setBusy(true)
    try {
      await request(`/api/coordinator/publications/candidates/${candidate.id}/discard`, {
        method: 'POST', body: { motivo: discardReason.trim() },
      })
      setMessage('La candidatura fue descartada. Se conservó su origen y el motivo en el registro.')
      setDiscardReason('')
      await openCandidate(candidate.id)
      await loadCandidates()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function linkResearcher(code) {
    setError(''); setMessage(''); setBusy(true)
    try {
      await request(`/api/coordinator/publications/candidates/${candidate.id}/investigators`, {
        method: 'POST', body: { codigo_ucsm: code },
      })
      setMessage('Investigador vinculado como pendiente de revisión.')
      await openCandidate(candidate.id)
      await loadCandidates()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function decideLink(code, resultado) {
    if (resultado !== 'aceptada' && !reason.trim()) {
      setError('Indica el motivo para rechazar o marcar como duplicado.')
      return
    }
    setError(''); setMessage(''); setBusy(true)
    try {
      await request(`/api/coordinator/publications/candidates/${candidate.id}/investigators/${code}/decision`, {
        method: 'POST', body: { resultado, motivo: reason.trim() || null },
      })
      setMessage(resultado === 'aceptada'
        ? 'Vínculo aprobado y publicación consolidada en el Histórico.'
        : 'La decisión quedó registrada en la candidatura.')
      setReason('')
      await openCandidate(candidate.id)
      await loadCandidates()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return <div className="page-stack">
    {error && <Alert kind="error">{error}</Alert>}{message && <Alert>{message}</Alert>}
    <section className="panel">
      <h2>Importar archivo de Pure</h2>
      <p className="muted">Sube la exportación CSV recibida. La previsualización valida el formato y no guarda datos. Al confirmar, el sistema guarda las filas válidas y consolida automáticamente las que tengan autor vinculado por UUID exacto, campos obligatorios válidos y ningún DOI duplicado. El resto queda en candidaturas para revisión. Los campos opcionales fuera de límite se omiten del catálogo y se conservan en el JSON original. No se consulta la API de Pure, Scopus ni ORCID.</p>
      <div className="pure-upload">
        <label className="field"><span>Archivo CSV (máximo 50 MB)</span><input type="file" accept=".csv,text/csv" onChange={(event) => fileChanged(event.target.files?.[0] || null)} /></label>
        <div className="form-actions"><button className="button button-outline" disabled={!file || busy} onClick={previewFile}>{busy ? 'Validando…' : 'Previsualizar CSV'}</button><button className="button button-primary" disabled={!file || !preview?.validas || busy} onClick={importFile}>Guardar como candidaturas</button></div>
      </div>
      {preview && <div className="import-preview">
        <div className="import-stats"><span>Filas: <strong>{preview.filas}</strong></span><span>Válidas: <strong>{preview.validas}</strong></span><span>Inválidas: <strong>{preview.invalidas}</strong></span><span>UUID repetidos: <strong>{preview.uuid_repetidos}</strong></span><span>DOI repetidos: <strong>{preview.doi_repetidos}</strong></span></div>
        {preview.errores.length > 0 && <div className="alert alert-warning"><strong>Filas que requieren corrección:</strong><ul>{preview.errores.map((item) => <li key={`${item.linea}-${item.mensaje}`}>Línea {item.linea}: {item.mensaje}</li>)}</ul></div>}
        {preview.muestra.length > 0 && <div className="table-scroll"><table><thead><tr><th>UUID</th><th>Título</th><th>Año</th><th>Tipo Pure</th><th>DOI</th></tr></thead><tbody>{preview.muestra.map((item) => <tr key={item.uuid}><td>{item.uuid}</td><td>{item.titulo}</td><td>{item.anio}</td><td>{item.tipo || '—'}</td><td>{item.doi || '—'}</td></tr>)}</tbody></table></div>}
      </div>}
      {importSummary && <div className="import-stats import-result">
        <span>Candidaturas creadas: <strong>{importSummary.candidatas_creadas}</strong></span>
        <span>Ya en Histórico: <strong>{importSummary.ya_en_historico}</strong></span>
        <span>Ya importadas: <strong>{importSummary.ya_importadas}</strong></span>
        <span>Posibles coincidencias DOI para revisar: <strong>{importSummary.posibles_duplicados_doi}</strong></span>
        <span>Vínculos exactos por ID Pure: <strong>{importSummary.vinculos_pure_exactos}</strong></span>
        <span>Campos opcionales omitidos por límites: <strong>{importSummary.campos_opcionales_omitidos}</strong></span>
      </div>}
      {importSummary && importSummary.candidatas_creadas > 0 && importSummary.vinculos_pure_exactos === 0 && <Alert kind="warning">No se encontró ningún vínculo por UUID de persona. Verifica que el CSV incluya esos UUID y que los investigadores aprobados tengan su ID Pure registrado en la sección Investigadores. No se atribuye autoría por coincidencia de nombre.</Alert>}
      {importSummary?.revision_lote && <section className="import-batch-review">
        <h3>Resultado de consolidación automática</h3>
        <div className="import-stats">
          <span>Total del lote: <strong>{importSummary.revision_lote.total}</strong></span>
          <span>Consolidadas automáticamente: <strong>{importSummary.revision_lote.consolidadas}</strong></span>
          <span>Pendientes de revisión: <strong>{importSummary.revision_lote.revision_manual}</strong></span>
        </div>
        {importSummary.revision_lote.muestra_aptas.length > 0 && <details className="source-value">
          <summary>Ver ejemplos aptos para consolidación (hasta 10)</summary>
          <ul>{importSummary.revision_lote.muestra_aptas.map((item) => <li key={item.id}><strong>{item.titulo}</strong> · {item.vinculos_exactos.length} vínculo(s) exacto(s)</li>)}</ul>
        </details>}
        {importSummary.revision_lote.motivos_revision.length > 0 && <ul className="batch-reasons">
          {importSummary.revision_lote.motivos_revision.map((item) => <li key={item.motivo}>{item.motivo}: {item.cantidad}</li>)}
        </ul>}
        {importSummary.revision_lote.muestra_revision.length > 0 && <details className="source-value">
          <summary>Ver ejemplos que quedan para revisión manual</summary>
          <ul>{importSummary.revision_lote.muestra_revision.map((item) => <li key={item.id}><strong>{item.titulo}</strong>: {item.motivos.join(' ')}</li>)}</ul>
        </details>}
        {importSummary.revision_lote.campos_opcionales_omitidos > 0 && <p className="small-muted">Se omitieron {importSummary.revision_lote.campos_opcionales_omitidos} campos opcionales que excedían límites; el valor original sigue guardado en los metadatos de Pure.</p>}
        {importSummary.revision_lote.revision_manual > 0
          ? <p className="muted">Los casos pendientes siguen en «Candidaturas de Pure». Abre uno para revisar sus motivos y corregirlo; al guardar, el lote vuelve a procesar automáticamente los casos que ya cumplan los criterios.</p>
          : <p className="notice">Todas las candidaturas del lote se procesaron automáticamente o ya estaban consolidadas.</p>}
      </section>}
    </section>
    <div className="publication-layout">
      <section className="panel publication-list">
        <div className="section-title-row"><div><h2>Candidaturas de Pure</h2><p className="muted">{candidates.total} registro(s); se muestran 50 por página.</p></div></div>
        <form className="search-bar" onSubmit={(event) => { event.preventDefault(); setPage(0); setSearch(searchTerm) }}>
          <TextField label="Buscar título, UUID o DOI" value={searchTerm} onChange={setSearchTerm} />
          <button className="button button-primary"><BsSearch aria-hidden="true" />Buscar</button>
        </form>
        <div className="publication-results">{candidates.items.map((item) => <button className={`publication-result${candidate?.id === item.id ? ' selected' : ''}`} key={item.id} onClick={() => openCandidate(item.id)}>
          <strong>{item.titulo}</strong><span>{item.anio_publicacion} · {item.tipo || 'Tipo sin especificar'}</span><small>{item.doi_normalizado || item.id_fuente} · {item.pendientes} vínculo(s) pendiente(s)</small>
        </button>)}</div>
        {!candidates.items.length && <div className="empty-state">No hay candidaturas para mostrar. Previsualiza y carga un CSV de Pure.</div>}
        <div className="form-actions"><button className="button button-outline" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Anterior</button><button className="button button-outline" disabled={(page + 1) * 50 >= candidates.total} onClick={() => setPage((value) => value + 1)}>Siguiente</button></div>
      </section>
      <section className="panel">
        <h2>Depurar y revisar</h2>
        {!candidate ? <p className="muted">Selecciona una candidatura. Se comparan UUID exactos y se señalan coincidencias DOI; no se fusionan registros automáticamente.</p> : <>
          <p><strong>{candidate.curacion.title}</strong><br /><span className="small-muted">Pure UUID {candidate.id_fuente} · estado {candidate.estado}</span></p>
          {candidate.metadatos_origen.curacion_automatica?.campos_omitidos?.length > 0 && <Alert kind="warning">
            Se omitieron del catálogo algunos campos opcionales fuera de límite; sus valores originales siguen en el JSON de Pure.
            <ul>{candidate.metadatos_origen.curacion_automatica.campos_omitidos.map((item, index) => <li key={`${item.campo}-${index}`}>{item.campo}: {item.motivo}</li>)}</ul>
          </Alert>}
          {candidate.posible_duplicado_doi && <Alert kind="warning">Se encontró un DOI igual en otro registro. Revisa la coincidencia; el sistema no fusiona publicaciones automáticamente.</Alert>}
          {candidate.estado === 'consolidada' && <Alert>Esta publicación ya se consolidó en el Histórico. Puedes revisar otros vínculos pendientes.</Alert>}
          {candidate.estado === 'pendiente' ? <form className="form-grid candidate-form" onSubmit={saveCuration}>
            {candidate.curacion.abstract?.length > 4000 && <Alert kind="warning">El resumen de Pure excede los 4.000 caracteres permitidos por el catálogo. Acórtalo antes de guardar; el texto original se conserva en los metadatos.</Alert>}
            {candidate.curacion.journal_number?.length > 10 && <Alert kind="warning">El número de revista excede los 10 caracteres del catálogo y se dejó vacío para que decidas qué conservar. El original permanece en los metadatos.<details className="source-value"><summary>Ver valor original</summary><pre>{candidate.curacion.journal_number}</pre></details></Alert>}
            {candidate.curacion.bibliographical_note?.length > 500 && <Alert kind="warning">La nota bibliográfica excede los 500 caracteres del catálogo y se dejó vacía. Puedes resumirla o dejarla fuera; el original permanece en los metadatos.<details className="source-value"><summary>Ver valor original</summary><pre>{candidate.curacion.bibliographical_note}</pre></details></Alert>}
            {candidate.curacion.keywords_groups?.some((value) => value.length > 100) && <Alert kind="warning">Una palabra clave excede los 100 caracteres permitidos. Acórtala o elimínala antes de guardar; el original permanece en los metadatos.</Alert>}
            <TextField label="Título" value={curation?.title} onChange={(v) => updateCuration('title', v)} required maxLength={500} />
            <TextField label="Año" type="number" min={1900} max={2100} value={curation?.publication_year} onChange={(v) => updateCuration('publication_year', v)} required />
            <TextField label="Tipo Pure" value={curation?.type} onChange={(v) => updateCuration('type', v)} required maxLength={50} />
            <label className="field"><span>Revisión por pares<b className="required"> *</b></span><select required value={curation?.peer_review ?? ''} onChange={(event) => updateCuration('peer_review', event.target.value)}><option value="">Selecciona un valor</option><option value="true">Sí</option><option value="false">No</option></select></label>
            <TextField label="Idioma" value={curation?.language} onChange={(v) => updateCuration('language', v)} required maxLength={30} />
            <TextField label="Categoría" value={curation?.category} onChange={(v) => updateCuration('category', v)} required maxLength={50} />
            <TextField label="URL del portal Pure" type="url" value={curation?.portal_url} onChange={(v) => updateCuration('portal_url', v)} required maxLength={255} />
            <TextArea label="Contribuyentes (uno por línea)" value={curation?.contributors} onChange={(v) => updateCuration('contributors', v)} required rows={4} />
            <TextArea label="Identificadores (uno por línea)" value={curation?.identifiers} onChange={(v) => updateCuration('identifiers', v)} rows={2} />
            <TextArea label="Palabras clave (una por línea)" value={curation?.keywords_groups} onChange={(v) => updateCuration('keywords_groups', v)} rows={2} help="Máximo 100 caracteres por elemento." />
            <TextArea label="Resumen" value={curation?.abstract} onChange={(v) => updateCuration('abstract', v)} rows={4} maxLength={4000} help="Máximo 4.000 caracteres." />
            <TextField label="Número de revista" value={curation?.journal_number} onChange={(v) => updateCuration('journal_number', v)} maxLength={10} />
            <TextArea label="Nota bibliográfica" value={curation?.bibliographical_note} onChange={(v) => updateCuration('bibliographical_note', v)} rows={3} maxLength={500} help="Máximo 500 caracteres." />
            <TextArea label="Estado(s) de publicación (uno por línea)" value={curation?.publication_status} onChange={(v) => updateCuration('publication_status', v)} rows={2} help="Máximo 30 caracteres por elemento." />
            {sourceVolume != null && !sourceVolumeIsNumeric && <Alert kind="warning">Pure contiene el volumen «{sourceVolume}», pero el catálogo solo admite un entero. El campo queda vacío para que decidas si omitirlo; el valor original se conserva en los metadatos de la candidatura.</Alert>}
            <TextField label="Volumen (entero)" type="number" min={1} help={sourceVolume != null && !sourceVolumeIsNumeric ? `Valor original de Pure: ${sourceVolume}. Déjalo vacío para no cargarlo en el campo numérico del catálogo.` : undefined} value={curation?.volumen} onChange={(v) => updateCuration('volumen', v)} />
            <TextField label="Número de páginas" type="number" min={1} value={curation?.number_of_pages} onChange={(v) => updateCuration('number_of_pages', v)} />
            <TextField label="Páginas" value={curation?.pages} onChange={(v) => updateCuration('pages', v)} maxLength={15} />
            <div className="candidate-source-links field-span">
              <h3>Enlaces de Pure</h3>
              <p className="muted">Corrige o elimina los enlaces que excedan los límites del catálogo. La versión original se conserva en los metadatos de origen.</p>
              {curation?.links.map((link, index) => <div className="candidate-source-link" key={`${link.pure_id || 'nuevo'}-${index}`}>
                {link.url?.length > 255 && <Alert kind="warning">Esta URL excede los 255 caracteres del catálogo; acórtala o elimina el enlace.</Alert>}
                <TextField label="ID del enlace en Pure" type="number" min={1} value={link.pure_id} onChange={(v) => updateSourceLink(index, 'pure_id', v)} required />
                <TextField label="Tipo de enlace" value={link.link_type} onChange={(v) => updateSourceLink(index, 'link_type', v)} required maxLength={50} />
                <TextField label="URL" type="url" value={link.url} onChange={(v) => updateSourceLink(index, 'url', v)} required maxLength={255} />
                <TextField label="Descripción" value={link.description} onChange={(v) => updateSourceLink(index, 'description', v)} maxLength={100} />
                <button type="button" className="button button-danger" onClick={() => updateCuration('links', curation.links.filter((_, itemIndex) => itemIndex !== index))}>Quitar enlace</button>
              </div>)}
              <button type="button" className="button button-outline" onClick={() => updateCuration('links', [...curation.links, { pure_id: '', link_type: '', url: '', description: '' }])}>Agregar enlace</button>
            </div>
            <div className="form-actions field-span"><button className="button button-outline" disabled={busy}>{busy ? 'Guardando…' : 'Guardar depuración'}</button></div>
          </form> : <Alert>La candidatura ya no está pendiente; su depuración no se puede modificar.</Alert>}
          {candidate.estado === 'pendiente' && <div className="candidate-discard">
            <TextArea label="Motivo para descartar esta candidatura" value={discardReason} onChange={setDiscardReason} rows={2} />
            <button className="button button-danger" disabled={busy || !discardReason.trim()} onClick={discardCandidate}>Descartar candidatura</button>
          </div>}
          {candidate.estado !== 'descartada' && <div className="candidate-authors">
            <h3>Vincular con investigadores aprobados</h3>
            <p className="muted">Solo se proponen vínculos automáticos cuando el UUID de persona en Pure coincide exactamente con el ID Pure del perfil. Las demás coincidencias se seleccionan manualmente tras verificarlas.</p>
            <form className="search-bar" onSubmit={findResearchers}>
              <TextField label="Buscar investigador por nombre o código" value={researcherTerm} onChange={setResearcherTerm} />
              <button className="button button-outline"><BsSearch aria-hidden="true" />Buscar</button>
            </form>
            {researchers.map((item) => <div className="candidate-researcher" key={item.codigo_ucsm}>
              <span>{item.nombre} · {item.codigo_ucsm}</span><button className="button button-outline" disabled={busy} onClick={() => linkResearcher(item.codigo_ucsm)}>Vincular</button>
            </div>)}
            {candidate.investigadores.length > 0 ? <div className="candidate-links">{candidate.investigadores.map((link) => <div className="candidate-link" key={link.codigo_ucsm}>
              <div><strong>{link.nombre}</strong><small>{link.codigo_ucsm} · {link.estado_revision} · ID Pure: {link.pure_person_id || 'no registrado'}{link.coincidencia_pure_exacta ? ' · UUID de persona coincide' : ''}{link.motivo ? ` · ${link.motivo}` : ''}</small></div>
              {link.estado_revision === 'pendiente' && <div className="form-actions">
                <button className="button button-primary" disabled={busy} onClick={() => decideLink(link.codigo_ucsm, 'aceptada')}>Aprobar vínculo</button>
                <button className="button button-outline" disabled={busy || !reason.trim()} onClick={() => decideLink(link.codigo_ucsm, 'duplicada')}>Marcar duplicado</button>
                <button className="button button-danger" disabled={busy || !reason.trim()} onClick={() => decideLink(link.codigo_ucsm, 'rechazada')}>Rechazar vínculo</button>
              </div>}
            </div>)}</div> : <div className="empty-state">Aún no hay vínculos; busca el investigador y confirma su autoría antes de aprobar.</div>}
            {candidate.investigadores.some((link) => link.estado_revision === 'pendiente') && <TextArea label="Motivo para duplicar o rechazar" value={reason} onChange={setReason} rows={2} />}
          </div>}
        </>}
      </section>
    </div>
  </div>
}

function CoordinatorReports() {
  const { request } = useAuth()
  const [catalog, setCatalog] = useState([])
  const [issued, setIssued] = useState([])
  const [selectedQuery, setSelectedQuery] = useState('')
  const [result, setResult] = useState(null)
  const [reportDetail, setReportDetail] = useState(null)
  const [date, setDate] = useState(() => {
    const today = new Date()
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const reload = useCallback(async () => {
    const [queries, reports] = await Promise.all([
      request('/api/coordinator/reports/catalog'), request('/api/coordinator/reports/issued'),
    ])
    setCatalog(queries); setIssued(reports)
    if (queries.length) setSelectedQuery((current) => current || String(queries[0].id))
  }, [request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  async function runQuery() {
    if (!selectedQuery) return
    setError(''); setBusy(true); setResult(null)
    try { setResult(await request(`/api/coordinator/reports/queries/${selectedQuery}`)) }
    catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function generate() {
    setError(''); setMessage(''); setBusy(true)
    try {
      await request('/api/coordinator/reports/issued', { method: 'POST', body: { fecha: date } })
      setMessage(`Reporte del ${date} generado.`)
      setReportDetail(await request(`/api/coordinator/reports/issued/${date}`))
      await reload()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  async function openReport(reportDate) {
    setError(''); setReportDetail(null)
    try { setReportDetail(await request(`/api/coordinator/reports/issued/${reportDate}`)) }
    catch (problem) { setError(problem.message) }
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Análisis institucional</p><h1>Reportes</h1><p>Ejecuta consultas de solo lectura y revisa los cortes diarios generados.</p></div>
    {error && <Alert kind="error">{error}</Alert>}{message && <Alert>{message}</Alert>}
    <section className="panel">
      <div className="section-title-row"><div><p className="eyebrow">Consultas disponibles</p><h2>Catálogo de reportes</h2></div><span className="status">{catalog.length} consultas</span></div>
      <div className="report-query-bar"><label className="field"><span>Consulta</span><select value={selectedQuery} onChange={(event) => setSelectedQuery(event.target.value)}>{catalog.map((item) => <option key={item.id} value={item.id}>{String(item.id).padStart(2, '0')} · {item.titulo}{item.usa_join ? ' · JOIN' : ''} ({item.procedimiento})</option>)}</select></label><button className="button button-primary" disabled={!selectedQuery || busy} onClick={runQuery}>{busy ? 'Ejecutando…' : 'Ejecutar consulta'}</button></div>
      {result && <div className="report-result"><h3>{result.titulo} · {result.filas.length} fila(s)</h3>{result.filas.length ? <div className="table-scroll"><table><thead><tr>{result.columnas.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.filas.map((row, index) => <tr key={index}>{row.map((value, cell) => <td key={cell}>{value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>)}</tr>)}</tbody></table></div> : <div className="empty-state">La consulta no devolvió resultados.</div>}</div>}
    </section>
    <section className="panel">
      <div className="section-title-row"><div><p className="eyebrow">Cortes guardados</p><h2>Generar reporte</h2></div></div>
      <div className="report-generation"><label className="field"><span>Fecha del reporte</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} required /></label><button className="button button-primary" disabled={busy || !date} onClick={generate}>{busy ? 'Generando…' : 'Generar reporte'}</button></div>
      <div className="report-history">
        <div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Coordinador</th><th></th></tr></thead><tbody>{issued.map((item) => <tr key={`${item.fecha}-${item.coordinador}`}><td>{item.fecha}</td><td>{item.coordinador}</td><td><button className="text-link action-link" onClick={() => openReport(item.fecha)}>Ver detalle</button></td></tr>)}</tbody></table></div>
        {!issued.length && <div className="empty-state">Aún no se han generado reportes.</div>}
        {reportDetail && <pre className="report-detail">{reportDetail.detalle}</pre>}
      </div>
    </section>
  </div>
}

function InvestigatorHome() {
  const { request } = useAuth()
  const [application, setApplication] = useState(null)
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const reload = useCallback(async () => {
    const app = await request('/api/researcher/application')
    setApplication(app)
    if (app.estado === 'aprobada') {
      setProfile(await request('/api/researcher/profile'))
    } else setProfile(null)
  }, [request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!application) return <div className="loading">Cargando tu solicitud…</div>
  const form = application.formulario
  return (
    <div className="page-stack">
      <div className="page-heading"><p className="eyebrow">Espacio del investigador</p><h1>Hola, {form.nombres}</h1><p>Consulta el estado y las acciones disponibles para tu perfil.</p></div>
      <section className="panel status-panel">
        <div className="status-heading"><div><p className="eyebrow">Estado de postulación</p><h2><StatusBadge value={application.estado} /></h2></div><span className="small-muted">Versión {application.version}</span></div>
        {application.estado === 'pendiente_revision' && <p>Tu postulación está en la bandeja del coordinador. Las verificaciones externas son evidencia y no producen aprobación automática.</p>}
        {application.estado === 'observada' && <><Alert kind="warning">{application.ultima_observacion || 'El coordinador solicita una corrección.'}</Alert><h3>Corregir y reenviar</h3><ApplicationForm initial={form} isCorrection onSubmit={async (payload) => { await request('/api/researcher/application', { method: 'PUT', body: payload }); await reload() }} submitLabel="Enviar correcciones" /></>}
        {application.estado === 'rechazada' && <Alert kind="error">{application.ultima_observacion || 'La solicitud fue rechazada. Comunícate con el coordinador para recibir orientación.'}</Alert>}
        {application.estado === 'aprobada' && profile && <div className="profile-summary"><h3>Perfil aprobado</h3><dl className="details-grid"><dt>Código institucional</dt><dd>{profile.codigo_ucsm}</dd><dt>Correo</dt><dd>{profile.correo}</dd><dt>ORCID</dt><dd><a href={`https://orcid.org/${profile.orcid}`} target="_blank" rel="noreferrer">{profile.orcid}</a></dd><dt>Pure</dt><dd>{profile.pure_estado === 'registrado_manual' ? `Registrado · ${profile.pure_person_id}` : 'Pendiente de registro manual por el coordinador'}</dd></dl></div>}
      </section>
      <section className="panel"><h2>Verificaciones y revisiones</h2><HistoryList verifications={application.verificaciones} revisions={application.revisiones} /></section>
    </div>
  )
}

function InvestigatorPatents() {
  const { request } = useAuth()
  const [profile, setProfile] = useState(null)
  const [patents, setPatents] = useState([])
  const [error, setError] = useState('')
  const [approved, setApproved] = useState(null)
  const [showPatentForm, setShowPatentForm] = useState(false)
  const [editingPatent, setEditingPatent] = useState(null)
  const reload = useCallback(async () => {
    const application = await request('/api/researcher/application')
    if (application.estado !== 'aprobada') {
      setApproved(false)
      setProfile(null)
      setPatents([])
      return
    }
    setApproved(true)
    const [person, requests] = await Promise.all([
      request('/api/researcher/profile'),
      request('/api/researcher/patents'),
    ])
    setProfile(person)
    setPatents(requests)
  }, [request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  if (error) return <Alert kind="error">{error}</Alert>
  if (approved === false) return <section className="panel"><h1>Mis solicitudes de patente</h1><Alert kind="warning">Esta sección se habilita cuando el coordinador apruebe tu perfil de investigador.</Alert><Link className="button button-outline" to="/investigator">Volver a mi solicitud</Link></section>
  if (!profile) return <div className="loading">Cargando tus patentes…</div>
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Propiedad intelectual</p><h1>Mis solicitudes de patente</h1><p>Registra una solicitud y consulta su estado por separado de tu postulación de investigador.</p></div>
    <section className="panel">
      <div className="section-title-row"><div><p className="eyebrow">Solicitudes</p><h2>Mis patentes</h2></div><button className="button button-primary" onClick={() => setShowPatentForm(!showPatentForm)}>{showPatentForm ? 'Cerrar formulario' : 'Nueva solicitud'}</button></div>
      {showPatentForm && <PatentForm onSubmit={async (payload) => { await request('/api/researcher/patents', { method: 'POST', body: payload }); setShowPatentForm(false); await reload() }} submitLabel="Enviar al coordinador" defaultInventor={profile.codigo_ucsm} />}
      <PatentList requests={patents} onEdit={setEditingPatent} />
      {editingPatent && <div className="panel patent-correction"><h3>Corregir solicitud observada</h3>{editingPatent.revisiones?.at(-1)?.motivo && <Alert kind="warning">{editingPatent.revisiones.at(-1).motivo}</Alert>}<PatentForm key={editingPatent.id} initial={editingPatent} onSubmit={async (payload) => { await request(`/api/researcher/patents/${editingPatent.id}`, { method: 'PUT', body: payload }); setEditingPatent(null); await reload() }} submitLabel="Reenviar correcciones" defaultInventor={profile.codigo_ucsm} /></div>}
    </section>
  </div>
}

function HistoryList({ verifications = [], revisions = [] }) {
  if (!verifications.length && !revisions.length) return <p className="muted">Aún no se registran verificaciones ni decisiones.</p>
  return <div className="table-scroll"><table><thead><tr><th>Tipo</th><th>Fuente / resultado</th><th>Versión</th><th>Detalle</th></tr></thead><tbody>
    {verifications.map((item, index) => <tr key={`v-${index}`}><td>Verificación {item.metodo}</td><td>{item.fuente} · {item.resultado}</td><td>{item.numero_version}</td><td>{item.nota || item.referencia_evidencia || '—'}</td></tr>)}
    {revisions.map((item, index) => <tr key={`r-${index}`}><td>Decisión del coordinador</td><td>{item.resultado}</td><td>{item.numero_version}</td><td>{item.motivo || 'Sin observaciones'}</td></tr>)}
  </tbody></table></div>
}

function PatentForm({ onSubmit, defaultInventor = '', initial = null, submitLabel }) {
  const [fields, setFields] = useState(() => ({
    n_patente: initial?.n_patente || '', titulo: initial?.titulo_patente || '',
    editorial: initial?.editorial || 'INDECOPI', fecha_registro: String(initial?.fecha_registro || '').slice(0, 10),
    cip: initial?.cip || '', pais: initial?.pais || 'Perú',
    inventores: (initial?.inventores || [defaultInventor]).filter(Boolean).join(', '),
    ocde: (initial?.clasificacion_ocde || []).map((item) => `${item.campo}|${item.objetivo}`).join('\n'),
  }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const update = (key, value) => setFields((current) => ({ ...current, [key]: value }))
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    const pairs = fields.ocde.split('\n').map((line) => line.split('|').map((part) => part.trim())).filter((pair) => pair.length === 2)
    const payload = {
      n_patente: fields.n_patente, titulo: fields.titulo, editorial: fields.editorial,
      fecha_registro: fields.fecha_registro, cip: fields.cip, pais: fields.pais,
      inventores: fields.inventores.split(/[,\s]+/).filter(Boolean).map(Number),
      clasificacion_ocde: pairs.map(([campo, objetivo]) => ({ campo, objetivo })),
    }
    try { await onSubmit(payload) } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return <form className="form-grid nested-form" onSubmit={submit}>
    {error && <Alert kind="error">{error}</Alert>}
    <TextField label="Número de patente" name="n_patente" value={fields.n_patente} onChange={(v) => update('n_patente', v)} required help="Formato, por ejemplo PE-123456." />
    <TextField label="Título" name="titulo" value={fields.titulo} onChange={(v) => update('titulo', v)} required />
    <TextField label="Entidad registradora" name="editorial" value={fields.editorial} onChange={(v) => update('editorial', v)} required />
    <TextField label="Fecha de registro" name="fecha_registro" type="date" value={fields.fecha_registro} onChange={(v) => update('fecha_registro', v)} required />
    <TextField label="Clasificación CIP" name="cip" value={fields.cip} onChange={(v) => update('cip', v)} required />
    <TextField label="País" name="pais" value={fields.pais} onChange={(v) => update('pais', v)} required />
    <TextArea label="Códigos institucionales de inventores (separados por coma)" value={fields.inventores} onChange={(v) => update('inventores', v)} required rows={2} />
    <TextArea label="Clasificación OCDE (una línea: Campo | Objetivo)" value={fields.ocde} onChange={(v) => update('ocde', v)} required rows={3} />
    <div className="form-actions field-span"><button className="button button-primary" disabled={busy}>{busy ? 'Enviando…' : submitLabel}</button></div>
  </form>
}

function PatentList({ requests, onOpen, onEdit }) {
  if (!requests?.length) return <div className="empty-state">Todavía no hay solicitudes de patente.</div>
  return <div className="table-scroll"><table><thead><tr><th>Número</th><th>Título</th><th>Estado</th><th>Versión</th>{(onOpen || onEdit) && <th>Acción</th>}</tr></thead><tbody>
    {requests.map((item) => <tr key={item.id}><td>{item.n_patente}</td><td>{item.titulo_patente}</td><td><StatusBadge value={item.estado} /></td><td>{item.version_actual}</td>{onOpen && <td><Link className="text-link" to={`/coordinator/patents/${item.id}`}>Revisar</Link></td>}{onEdit && <td>{item.estado === 'observada' && <button className="text-link action-link" onClick={() => onEdit(item)}>Corregir</button>}</td>}</tr>)}
  </tbody></table></div>
}

function CoordinatorHome({ initialTab = 'applications' }) {
  const [applications, setApplications] = useState([])
  const [patents, setPatents] = useState([])
  const [pureList, setPureList] = useState([])
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const [tab, setTab] = useState(
    ['applications', 'patents', 'pure'].includes(requestedTab) ? requestedTab : initialTab,
  )
  const [error, setError] = useState('')
  const [busyPure, setBusyPure] = useState(null)
  const { request } = useAuth()
  const [pureValues, setPureValues] = useState({})
  const reload = useCallback(async () => {
    const [apps, patentsList, pendingPure] = await Promise.all([
      request('/api/coordinator/applications'), request('/api/coordinator/patents'),
      request('/api/coordinator/pure-pending'),
    ])
    setApplications(apps); setPatents(patentsList); setPureList(pendingPure)
  }, [request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  async function savePure(code) {
    setBusyPure(code); setError('')
    try {
      await request(`/api/coordinator/investigators/${code}/pure`, { method: 'POST', body: { pure_person_id: pureValues[code] || '' } })
      await reload()
    } catch (problem) { setError(problem.message) } finally { setBusyPure(null) }
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Gestión institucional</p><h1>Bandeja del coordinador</h1><p>Revisa cada caso, guarda evidencia y registra tu decisión. Las verificaciones API no aprueban solicitudes.</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    <div className="tab-row" role="tablist">{[['applications', `Postulaciones (${applications.length})`], ['patents', `Patentes (${patents.length})`], ['pure', `Pure pendiente (${pureList.length})`]].map(([key, label]) => <button key={key} className={`tab-button ${tab === key ? 'selected' : ''}`} onClick={() => setTab(key)} role="tab" aria-selected={tab === key}>{label}</button>)}</div>
    {tab === 'applications' && <section className="panel"><h2>Postulaciones por revisar</h2>{applications.length ? <div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Investigador</th><th>Correo</th><th>Código</th><th>Estado</th><th>Versión</th><th></th></tr></thead><tbody>{applications.map((item) => <tr key={item.id}><td>{new Date(item.creada_en).toLocaleDateString()}</td><td>{item.nombres} {item.apellido_paterno}</td><td>{item.correo_elec}</td><td>{item.codigo_ucsm}</td><td><StatusBadge value={item.estado} /></td><td>{item.version_actual}</td><td><Link className="text-link" to={`/coordinator/applications/${item.id}`}>Abrir revisión</Link></td></tr>)}</tbody></table></div> : <div className="empty-state">No hay postulaciones pendientes de revisión.</div>}</section>}
    {tab === 'patents' && <section className="panel"><h2>Solicitudes de patente por revisar</h2><PatentList requests={patents} onOpen /></section>}
    {tab === 'pure' && <section className="panel"><h2>Altas manuales en Pure</h2><p className="muted">Busca y registra el identificador de persona en la instancia institucional. No se hacen llamadas a Pure API.</p>{pureList.length ? <div className="pure-list">{pureList.map((item) => <div className="pure-row" key={item.codigo_ucsm}><div><strong>{item.nombres} {item.apellido_paterno} {item.apellido_materno}</strong><small>{item.codigo_ucsm} · {item.correo_elec}</small></div><input aria-label={`ID Pure de ${item.nombres}`} value={pureValues[item.codigo_ucsm] || ''} onChange={(event) => setPureValues((current) => ({ ...current, [item.codigo_ucsm]: event.target.value }))} placeholder="ID/UUID de Pure" /><button className="button button-primary" disabled={busyPure === item.codigo_ucsm} onClick={() => savePure(item.codigo_ucsm)}>{busyPure === item.codigo_ucsm ? 'Guardando…' : 'Registrar'}</button></div>)}</div> : <div className="empty-state">No hay perfiles pendientes de alta manual.</div>}</section>}
  </div>
}

function ApplicationReview() {
  const { id } = useParams()
  const { request } = useAuth()
  const navigate = useNavigate()
  const [application, setApplication] = useState(null)
  const [error, setError] = useState('')
  const [orcidMessage, setOrcidMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [decisionReason, setDecisionReason] = useState('')
  const [manual, setManual] = useState({ fuente: 'codigo_ucsm', resultado: 'requiere_revision', referencia: '', nota: '' })
  const reload = useCallback(async () => {
    setApplication(await request(`/api/coordinator/applications/${id}`))
  }, [id, request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  async function action(path, body) {
    setError(''); setBusy(true)
    try { await request(path, { method: 'POST', body }); await reload() }
    catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  if (error && !application) return <Alert kind="error">{error}</Alert>
  if (!application) return <div className="loading">Cargando postulación…</div>
  const form = application.formulario
  async function verifyOrcid() {
    setError(''); setOrcidMessage(''); setBusy(true)
    try {
      const result = await request(`/api/coordinator/applications/${id}/orcid-check`, { method: 'POST' })
      setOrcidMessage(`${result.resultado.replaceAll('_', ' ')}: ${result.nota}`)
      await reload()
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Revisión de postulación · versión {application.version}</p><h1>{form.nombres} {form.apellido_paterno} {form.apellido_materno}</h1><p><StatusBadge value={application.estado} /> · Código institucional {form.codigo_ucsm}</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    <section className="panel"><h2>Datos declarados</h2><dl className="details-grid">{Object.entries({
      DNI: form.dni, Correo: form.correo, Género: form.genero, 'Fecha de nacimiento': form.fecha_nacimiento,
      Escuela: form.escuela, Celular: form.celular, ORCID: form.orcid, 'Scopus ID': form.scopus_id || 'No registrado',
      'CTI Vitae': form.link_cti, 'Referencia de foto': form.foto, 'Resumen académico': form.resumen,
      ODS: form.ods.join(', '), 'Intereses de investigación': form.intereses.join(', '),
    }).map(([label, value]) => <div className="detail-pair" key={label}><dt>{label}</dt><dd>{value || '—'}</dd></div>)}</dl></section>
    <section className="panel"><div className="section-title-row"><h2>Verificación ORCID</h2><button className="button button-primary" disabled={busy || application.estado !== 'pendiente_revision'} onClick={verifyOrcid}>{busy ? 'Consultando…' : 'Consultar API pública'}</button></div><p className="muted">Consulta la existencia del registro ORCID. No comprueba afiliación institucional ni decide la postulación.</p>{orcidMessage && <Alert>{orcidMessage}</Alert>}<VerificationList items={application.verificaciones.filter((item) => item.fuente === 'orcid')} /></section>
    <section className="panel"><h2>Registrar verificación manual</h2><div className="form-grid">
      <label className="field"><span>Fuente</span><select value={manual.fuente} onChange={(event) => setManual({ ...manual, fuente: event.target.value })}>{['codigo_ucsm', 'afiliacion', 'orcid', 'scopus', 'cti_vitae', 'renacyt'].map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
      <label className="field"><span>Resultado</span><select value={manual.resultado} onChange={(event) => setManual({ ...manual, resultado: event.target.value })}>{['confirmado', 'no_confirmado', 'no_disponible', 'error_consulta', 'requiere_revision'].map((value) => <option key={value}>{value}</option>)}</select></label>
      <TextField label="Referencia de evidencia (opcional)" value={manual.referencia} onChange={(v) => setManual({ ...manual, referencia: v })} />
      <TextField label="Nota" value={manual.nota} onChange={(v) => setManual({ ...manual, nota: v })} />
      <div className="form-actions field-span"><button className="button button-outline" disabled={busy || application.estado !== 'pendiente_revision'} onClick={() => action(`/api/coordinator/applications/${id}/manual-verifications`, manual)}>Guardar verificación</button></div>
    </div></section>
    <section className="panel"><h2>Historial</h2><HistoryList verifications={application.verificaciones} revisions={application.revisiones} /></section>
    {application.estado === 'pendiente_revision' && <section className="panel"><h2>Decisión del coordinador</h2><TextArea label="Motivo para observar o rechazar (obligatorio en esas decisiones)" value={decisionReason} onChange={setDecisionReason} rows={3} /><div className="form-actions">
      <button className="button button-primary" disabled={busy} onClick={() => action(`/api/coordinator/applications/${id}/decision`, { resultado: 'aprobada' })}>Aprobar y crear perfil</button>
      <button className="button button-outline" disabled={busy || !decisionReason.trim()} onClick={() => action(`/api/coordinator/applications/${id}/observation`, { motivo: decisionReason })}>Observar para corrección</button>
      <button className="button button-danger" disabled={busy || !decisionReason.trim()} onClick={async () => { if (window.confirm('¿Rechazar esta postulación?')) await action(`/api/coordinator/applications/${id}/decision`, { resultado: 'rechazada', motivo: decisionReason }) }}>Rechazar</button>
      <button className="button button-quiet" onClick={() => navigate('/coordinator')}>Volver</button>
    </div></section>}
  </div>
}

function VerificationList({ items }) {
  if (!items.length) return <p className="muted">Aún no se registran resultados para esta fuente.</p>
  return <ul className="verification-list">{items.map((item, index) => <li key={`${item.fuente}-${index}`}><div><strong>{item.resultado.replaceAll('_', ' ')}</strong><small>{item.metodo} · versión {item.numero_version}</small></div><span>{item.nota || item.referencia_evidencia || 'Sin detalle adicional'}</span></li>)}</ul>
}

function PatentReview() {
  const { id } = useParams()
  const { request } = useAuth()
  const navigate = useNavigate()
  const [patent, setPatent] = useState(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const reload = useCallback(async () => {
    setPatent(await request(`/api/coordinator/patents/${id}`))
  }, [id, request])
  useEffect(() => { reload().catch((problem) => setError(problem.message)) }, [reload])
  async function decide(resultado) {
    setError(''); setBusy(true)
    try { await request(`/api/coordinator/patents/${id}/decision`, { method: 'POST', body: { resultado, motivo: reason || null } }); await reload() }
    catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  if (error && !patent) return <Alert kind="error">{error}</Alert>
  if (!patent) return <div className="loading">Cargando solicitud de patente…</div>
  return <div className="page-stack">
    <div className="page-heading"><p className="eyebrow">Solicitud de patente · versión {patent.version_actual}</p><h1>{patent.titulo_patente}</h1><p><StatusBadge value={patent.estado} /> · {patent.n_patente}</p></div>
    {error && <Alert kind="error">{error}</Alert>}
    <section className="panel"><h2>Datos de la solicitud</h2><dl className="details-grid">
      <dt>Solicitante</dt><dd>{patent.nombres} {patent.apellido_paterno} {patent.apellido_materno} · {patent.solicitante_codigo_ucsm}</dd>
      <dt>Entidad / país</dt><dd>{patent.editorial} · {patent.pais}</dd><dt>Fecha</dt><dd>{String(patent.fecha_registro).slice(0, 10)}</dd>
      <dt>CIP</dt><dd>{patent.cip}</dd><dt>Inventores</dt><dd>{patent.inventores.join(', ')}</dd>
      <dt>Clasificación OCDE</dt><dd>{patent.clasificacion_ocde.map((item) => `${item.campo} | ${item.objetivo}`).join('; ')}</dd>
    </dl></section>
    <section className="panel"><h2>Historial de revisión</h2>{patent.revisiones.length ? <div className="table-scroll"><table><thead><tr><th>Versión</th><th>Resultado</th><th>Motivo</th><th>Coordinador</th></tr></thead><tbody>{patent.revisiones.map((item) => <tr key={item.version_evaluada}><td>{item.version_evaluada}</td><td>{item.resultado}</td><td>{item.motivo || '—'}</td><td>{item.resuelto_por}</td></tr>)}</tbody></table></div> : <p className="muted">No hay revisiones previas.</p>}</section>
    {patent.estado === 'pendiente_revision' && <section className="panel"><h2>Resolver solicitud</h2><TextArea label="Motivo requerido para observar o rechazar" value={reason} onChange={setReason} rows={3} /><div className="form-actions">
      <button className="button button-primary" disabled={busy} onClick={() => decide('aprobada')}>Aprobar y crear patente definitiva</button>
      <button className="button button-outline" disabled={busy || !reason.trim()} onClick={() => decide('observada')}>Observar</button>
      <button className="button button-danger" disabled={busy || !reason.trim()} onClick={() => decide('rechazada')}>Rechazar</button>
      <button className="button button-quiet" onClick={() => navigate('/coordinator/applications?tab=patents')}>Volver</button>
    </div></section>}
  </div>
}

// --- Panel de administrador: CRUD genérico sobre las tablas -----------------
// Rol técnico de mantenimiento. Las columnas y tipos vienen del catálogo de
// PostgreSQL; la base sigue aplicando restricciones, claves foráneas y triggers.
const ADMIN_PAGE_SIZE = 25
const ADMIN_MASK = '********'

function adminCellText(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function adminInputValue(column, value) {
  if (value === null || value === undefined) return ''
  if (column.sensible) return ''
  if (Array.isArray(value) && column.tipo.endsWith('[]')) {
    return `{${value.map((item) => `"${String(item).replace(/["\\]/g, '\\$&')}"`).join(',')}}`
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function AdminField({ column, value, onChange, isNew }) {
  const disabled = column.solo_lectura || (!isNew && column.clave_primaria)
  const label = <span>{column.nombre}{!column.nullable && !column.por_defecto && !column.solo_lectura && <b className="required"> *</b>} <small className="small-muted">{column.tipo}</small></span>
  if (column.tipo === 'boolean') {
    return <label className="field">{label}<select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}><option value="">(vacío)</option><option value="true">true</option><option value="false">false</option></select></label>
  }
  if (column.tipo === 'json' || column.tipo === 'jsonb' || /character varying\((1\d{3,}|[2-9]\d{3,})\)|text/.test(column.tipo)) {
    return <label className="field field-span">{label}<textarea rows={3} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>
  }
  const type = column.sensible ? 'password' : column.tipo === 'date' ? 'date' : 'text'
  const placeholder = column.sensible ? (isNew ? 'Contraseña (se guarda como hash)' : 'Dejar vacío para no cambiar') : column.solo_lectura ? 'Automático' : ''
  return <label className="field">{label}<input type={type} value={value} disabled={disabled} placeholder={placeholder} autoComplete="new-password" onChange={(event) => onChange(event.target.value)} /></label>
}

function AdminRowForm({ data, row, onCancel, onSaved }) {
  const { request } = useAuth()
  const isNew = row === null
  const initial = useMemo(() => Object.fromEntries(data.columnas.map((column) => [column.nombre, isNew ? '' : adminInputValue(column, row[column.nombre])])), [data, row, isNew])
  const [values, setValues] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const changed = Object.fromEntries(data.columnas
        .filter((column) => !column.solo_lectura && values[column.nombre] !== initial[column.nombre])
        .map((column) => [column.nombre, values[column.nombre]]))
      if (isNew) {
        await request(`/api/admin/tables/${data.tabla}/rows`, { method: 'POST', body: { valores: changed } })
      } else {
        const clave = Object.fromEntries(data.clave_primaria.map((name) => [name, row[name]]))
        await request(`/api/admin/tables/${data.tabla}/rows`, { method: 'PUT', body: { clave, valores: changed } })
      }
      onSaved(isNew ? 'Registro creado.' : 'Registro actualizado.')
    } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  return (
    <form className="panel form-grid" onSubmit={submit}>
      <h2 className="form-section-title">{isNew ? `Nuevo registro en ${data.tabla}` : `Editar registro de ${data.tabla}`}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      {data.columnas.map((column) => <AdminField key={column.nombre} column={column} isNew={isNew} value={values[column.nombre]} onChange={(value) => setValues((current) => ({ ...current, [column.nombre]: value }))} />)}
      <p className="small-muted field-span">Un campo vacío se guarda como nulo. Las restricciones, claves foráneas y triggers de la base se siguen aplicando.</p>
      <div className="form-actions field-span"><button className="button button-primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button><button type="button" className="button button-quiet" onClick={onCancel}>Cancelar</button></div>
    </form>
  )
}

function AdminPanel() {
  const { request, csrf } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const table = searchParams.get('tabla') || ''
  const page = Number(searchParams.get('pagina') || 1)
  const search = searchParams.get('buscar') || ''
  const [tables, setTables] = useState([])
  const [tableFilter, setTableFilter] = useState('')
  const [data, setData] = useState(null)
  const [searchText, setSearchText] = useState(search)
  const [editing, setEditing] = useState(undefined)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { request('/api/admin/tables').then(setTables).catch((problem) => setError(problem.message)) }, [request])
  const loadRows = useCallback(async () => {
    if (!table) { setData(null); return }
    const query = new URLSearchParams({ pagina: String(page), tamano: String(ADMIN_PAGE_SIZE) })
    if (search) query.set('buscar', search)
    try { setData(await request(`/api/admin/tables/${encodeURIComponent(table)}/rows?${query}`)); setError('') } catch (problem) { setData(null); setError(problem.message) }
  }, [request, table, page, search])
  useEffect(() => { loadRows() }, [loadRows])

  function go(changes) {
    const next = new URLSearchParams(searchParams)
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)))
    setSearchParams(next)
    setEditing(undefined); setMessage('')
  }
  async function remove(row) {
    const clave = Object.fromEntries(data.clave_primaria.map((name) => [name, row[name]]))
    const label = Object.entries(clave).map(([key, value]) => `${key}=${value}`).join(', ')
    if (!window.confirm(`¿Eliminar el registro ${label} de ${data.tabla}? Esta acción no se puede deshacer.`)) return
    try {
      await sendRequest(`/api/admin/tables/${data.tabla}/rows`, { method: 'DELETE', body: { clave }, csrf })
      setMessage(`Registro ${label} eliminado.`); setError('')
      await loadRows()
    } catch (problem) { setError(problem.message); setMessage('') }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.tamano)) : 1
  const visibleTables = tables.filter((item) => item.nombre.includes(tableFilter.trim().toLowerCase()))
  const editable = data && data.clave_primaria.length > 0
  return (
    <div className="page-stack">
      <div className="page-heading"><p className="eyebrow">Administrador</p><h1>Datos del portal</h1><p>Consulta, crea, edita y elimina registros de cualquier tabla. Úselo solo para mantenimiento.</p></div>
      <div className="admin-layout">
        <aside className="panel admin-tables">
          <label className="field"><span>Tablas ({tables.length})</span><input value={tableFilter} placeholder="Filtrar…" onChange={(event) => setTableFilter(event.target.value)} /></label>
          <nav>{visibleTables.map((item) => <button key={item.nombre} type="button" className={`admin-table-link${item.nombre === table ? ' active' : ''}`} onClick={() => { setSearchText(''); go({ tabla: item.nombre, pagina: '', buscar: '' }) }}>{item.nombre}</button>)}</nav>
        </aside>
        <section className="admin-content">
          {error && <Alert kind="error">{error}</Alert>}
          {message && <Alert kind="success">{message}</Alert>}
          {!table && <div className="panel empty-state">Seleccione una tabla para ver sus registros.</div>}
          {editing !== undefined && data && <AdminRowForm key={editing === null ? 'nuevo' : JSON.stringify(data.clave_primaria.map((name) => editing[name]))} data={data} row={editing} onCancel={() => setEditing(undefined)} onSaved={async (text) => { setEditing(undefined); setMessage(text); setError(''); await loadRows() }} />}
          {data && (
            <div className="panel">
              <div className="section-title-row">
                <h2>{data.tabla} <small className="small-muted">{data.total} registro(s)</small></h2>
                <button type="button" className="button button-primary" onClick={() => { setEditing(null); setMessage('') }}>Nuevo registro</button>
              </div>
              <form className="admin-search" onSubmit={(event) => { event.preventDefault(); go({ buscar: searchText.trim(), pagina: '' }) }}>
                <input value={searchText} placeholder="Buscar en cualquier columna…" onChange={(event) => setSearchText(event.target.value)} />
                <button className="button button-outline button-compact">Buscar</button>
                {search && <button type="button" className="button button-quiet button-compact" onClick={() => { setSearchText(''); go({ buscar: '', pagina: '' }) }}>Limpiar</button>}
              </form>
              {!editable && <p className="notice">Esta tabla no tiene clave primaria: solo se puede consultar y agregar registros.</p>}
              <div className="table-scroll"><table>
                <thead><tr>{editable && <th>Acciones</th>}{data.columnas.map((column) => <th key={column.nombre}>{column.nombre}{column.clave_primaria ? ' 🔑' : ''}</th>)}</tr></thead>
                <tbody>{data.filas.map((row, index) => <tr key={editable ? data.clave_primaria.map((name) => row[name]).join('|') : index}>
                  {editable && <td className="admin-actions"><button type="button" className="button button-outline button-compact" onClick={() => { setEditing(row); setMessage(''); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Editar</button><button type="button" className="button button-danger button-compact" onClick={() => remove(row)}>Eliminar</button></td>}
                  {data.columnas.map((column) => <td key={column.nombre} title={adminCellText(row[column.nombre])}>{row[column.nombre] === ADMIN_MASK ? ADMIN_MASK : adminCellText(row[column.nombre]).slice(0, 80)}</td>)}
                </tr>)}</tbody>
              </table></div>
              {!data.filas.length && <div className="empty-state">No hay registros{search ? ' que coincidan con la búsqueda' : ''}.</div>}
              <div className="admin-pagination">
                <button type="button" className="button button-outline button-compact" disabled={page <= 1} onClick={() => go({ pagina: String(page - 1) })}>Anterior</button>
                <span>Página {page} de {totalPages}</span>
                <button type="button" className="button button-outline button-compact" disabled={page >= totalPages} onClick={() => go({ pagina: String(page + 1) })}>Siguiente</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

// --- Asistente de primer inicio (después del instalador de Windows) ---------
// Mientras config.ini diga [portal] configuracion_inicial = pendiente, todas
// las rutas llevan aquí. Paso 1: contraseña de la base. Paso 2: ORCID.
function SetupGate({ children }) {
  const location = useLocation()
  const [pendiente, setPendiente] = useState(null)
  useEffect(() => {
    sendRequest('/api/setup/status').then((data) => setPendiente(Boolean(data.pendiente))).catch(() => setPendiente(false))
  }, [location.pathname])
  if (pendiente === null) return <div className="loading">Cargando portal…</div>
  if (pendiente && location.pathname !== '/configuracion-inicial') return <Navigate to="/configuracion-inicial" replace />
  if (!pendiente && location.pathname === '/configuracion-inicial') return <Navigate to="/" replace />
  return children
}

function SetupHelp({ children }) {
  return <small className="setup-help">{children}</small>
}

function SetupWizard() {
  const { csrf } = useAuth()
  const navigate = useNavigate()
  const [estado, setEstado] = useState(null)
  const [paso, setPaso] = useState(1)
  const [clave, setClave] = useState({ nueva_clave: '', confirmacion: '' })
  const [orcidForm, setOrcidForm] = useState({ client_id: '', client_secret: '', environment: 'sandbox', redirect_uri: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    sendRequest('/api/setup/status').then((data) => {
      setEstado(data)
      setPaso(data.paso_base_datos ? 2 : 1)
      setOrcidForm((actual) => ({ ...actual, redirect_uri: data.redirect_uri_sugerida || '' }))
    }).catch((problem) => setError(problem.message))
  }, [])
  async function enviar(ruta, body, siguiente) {
    setBusy(true); setError('')
    try { await sendRequest(ruta, { method: 'POST', body, csrf }); siguiente() } catch (problem) { setError(problem.message) } finally { setBusy(false) }
  }
  if (!estado) return <div className="loading">Cargando configuración inicial…</div>
  const pasos = ['Base de datos', 'ORCID', 'Listo']
  return (
    <section className="panel setup-panel">
      <p className="eyebrow">Configuración inicial</p>
      <h1>Bienvenido al Sistema Gestor de Investigación</h1>
      <p className="muted">Antes del primer uso, complete estos pasos. Solo se piden una vez y se guardan en el archivo config.ini de esta computadora.</p>
      <ol className="setup-steps">{pasos.map((nombre, i) => <li key={nombre} className={paso === i + 1 ? 'active' : paso > i + 1 ? 'done' : ''}><span>{i + 1}</span>{nombre}</li>)}</ol>
      {error && <Alert kind="error">{error}</Alert>}

      {paso === 1 && <form className="form-grid" onSubmit={(event) => { event.preventDefault(); enviar('/api/setup/database', clave, () => setPaso(2)) }}>
        <h2 className="form-section-title">Paso 1. Contraseña de la base de datos</h2>
        <p className="field-span muted">El instalador creó la base de datos con una contraseña aleatoria. Cámbiela por una que usted conozca: se actualizará en PostgreSQL y en config.ini.</p>
        <PasswordField label="Nueva contraseña" name="nueva_clave" value={clave.nueva_clave} onChange={(v) => setClave({ ...clave, nueva_clave: v })} required autoComplete="new-password" help="Mínimo 12 caracteres. Sin comillas simples (') ni barras invertidas (\). Guárdela en un lugar seguro: la necesitará para entrar a pgAdmin o psql." />
        <PasswordField label="Confirmar contraseña" name="confirmacion" value={clave.confirmacion} onChange={(v) => setClave({ ...clave, confirmacion: v })} required autoComplete="new-password" help="Escriba la misma contraseña otra vez." />
        <div className="form-actions field-span"><button className="button button-primary" disabled={busy || clave.nueva_clave.length < 12}>{busy ? 'Guardando…' : 'Guardar y continuar'}</button></div>
      </form>}

      {paso === 2 && <form className="form-grid" onSubmit={(event) => { event.preventDefault(); enviar('/api/setup/orcid', orcidForm, () => setPaso(3)) }}>
        <h2 className="form-section-title">Paso 2. Inicio de sesión con ORCID</h2>
        <p className="field-span muted">Los investigadores confirman su ORCID iniciando sesión en orcid.org. Para eso, el portal necesita los datos de su aplicación registrada en ORCID. Entre a <strong>sandbox.orcid.org</strong> (pruebas) u <strong>orcid.org</strong> (oficial), abra su nombre → <strong>Developer tools</strong> y copie los datos de allí.</p>
        <label className="field"><span>Entorno de ORCID<b className="required"> *</b></span>
          <select value={orcidForm.environment} onChange={(event) => setOrcidForm({ ...orcidForm, environment: event.target.value })}>
            <option value="sandbox">Sandbox (pruebas) — sandbox.orcid.org</option>
            <option value="production">Producción (oficial) — orcid.org</option>
          </select>
          <SetupHelp>Elija el sitio donde registró la aplicación. Para el curso normalmente es Sandbox.</SetupHelp>
        </label>
        <TextField label="Client ID" name="client_id" value={orcidForm.client_id} onChange={(v) => setOrcidForm({ ...orcidForm, client_id: v.trim() })} required help="Aparece en Developer tools como «Client ID». Empieza con APP- (por ejemplo APP-ABCD1234EFGH5678)." />
        <PasswordField label="Client secret" name="client_secret" value={orcidForm.client_secret} onChange={(v) => setOrcidForm({ ...orcidForm, client_secret: v.trim() })} required autoComplete="off" help="En Developer tools, junto al Client ID, pulse «Show details» y copie el «Client secret». No lo comparta con nadie." />
        <label className="field field-span"><span>URI de redirección<b className="required"> *</b></span>
          <input value={orcidForm.redirect_uri} onChange={(event) => setOrcidForm({ ...orcidForm, redirect_uri: event.target.value.trim() })} />
          <SetupHelp>Debe ser exactamente igual a una de las «Redirect URIs» registradas en Developer tools. Para usar el portal en esta computadora, registre en ORCID: <code>{estado.redirect_uri_sugerida}</code></SetupHelp>
        </label>
        <p className="field-span muted">Al continuar, el portal comprueba los datos con ORCID. Si aún no tiene la aplicación registrada, puede omitir este paso y completarlo después en config.ini (sección [orcid]).</p>
        <div className="form-actions field-span">
          <button className="button button-primary" disabled={busy || !orcidForm.client_id || !orcidForm.client_secret}>{busy ? 'Comprobando con ORCID…' : 'Comprobar y guardar'}</button>
          <button type="button" className="button button-quiet" disabled={busy} onClick={() => enviar('/api/setup/orcid', { omitir: true }, () => setPaso(3))}>Omitir por ahora</button>
        </div>
      </form>}

      {paso === 3 && <div className="form-grid">
        <h2 className="form-section-title">Paso 3. Todo listo</h2>
        <p className="field-span">La configuración quedó guardada. Ya puede usar el portal con las cuentas de prueba o crear las suyas.</p>
        <div className="form-actions field-span"><button type="button" className="button button-primary" disabled={busy} onClick={() => enviar('/api/setup/finish', {}, () => navigate('/', { replace: true }))}>{busy ? 'Finalizando…' : 'Ir al portal'}</button></div>
      </div>}
    </section>
  )
}

function RouterApp() {
  return <AuthProvider><BrowserRouter><AppFrame><SetupGate><Routes>
    <Route path="/configuracion-inicial" element={<SetupWizard />} />
    <Route path="/" element={<Home />} />
    <Route path="/login/:role" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route element={<RequireRole role="investigator" />}>
      <Route path="/investigator" element={<InvestigatorHome />} />
      <Route path="/investigator/patents" element={<InvestigatorPatents />} />
    </Route>
    <Route element={<RequireRole role="coordinator" />}>
      <Route path="/coordinator" element={<CoordinatorDashboard />} />
      <Route path="/coordinator/applications" element={<CoordinatorHome key="applications" />} />
      <Route path="/coordinator/investigators" element={<CoordinatorInvestigators />} />
      <Route path="/coordinator/registered-patents" element={<CoordinatorPatentRegistry />} />
      <Route path="/coordinator/publications" element={<CoordinatorPublications />} />
      <Route path="/coordinator/reports" element={<CoordinatorReports />} />
      <Route path="/coordinator/applications/:id" element={<ApplicationReview />} />
      <Route path="/coordinator/patents/:id" element={<PatentReview />} />
    </Route>
    <Route element={<RequireRole role="admin" />}>
      <Route path="/admin" element={<AdminPanel />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></SetupGate></AppFrame></BrowserRouter></AuthProvider>
}

export default function App() {
  return <RouterApp />
}
