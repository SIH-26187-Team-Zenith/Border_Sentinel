import { useEffect,useRef,useState } from 'react'
import { createZone,deleteZone,listZones } from '../api/zones'
export default function ZoneEditor({ cameraId }) {
  const ref = useRef(null)
  const [points, setPoints] = useState([])
  const [zones, setZones] = useState([])
  const [name, setName] = useState('Restricted Zone')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    listZones(cameraId).then(setZones).catch((e) => setError(e.message))
  }, [cameraId])

  function click(e) {
    const r = ref.current.getBoundingClientRect()
    setPoints((p) => [
      ...p,
      {
        x: Math.round(((e.clientX - r.left) / r.width) * 1280),
        y: Math.round(((e.clientY - r.top) / r.height) * 720),
      },
    ])
  }

  async function save() {
    if (points.length < 3) return
    setSaving(true)
    try {
      const z = await createZone(cameraId, { name, points, enabled: true, trigger_object: 'person' })
      setZones((zs) => [...zs, z])
      setPoints([])
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-lg">
      <div className="border-b border-slate-800 p-4">
        <h2 className="text-sm font-semibold text-slate-200">Virtual fence / restricted zone</h2>
        <p className="mt-1 text-xs text-slate-500">
          Click at least 3 points to draw a polygon. Coordinates are stored and the AI service refreshes them automatically.
        </p>
      </div>
      <div className="p-4">
        <div
          ref={ref}
          onClick={click}
          className="relative aspect-video cursor-crosshair overflow-hidden rounded-lg border border-slate-800 bg-[linear-gradient(135deg,#0f172a,#020617)]"
        >
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1280 720" preserveAspectRatio="none">
            <polygon
              points={points.map((p) => `${p.x},${p.y}`).join(' ')}
              fill="rgba(239,68,68,.12)"
              stroke="rgba(248,113,113,.9)"
              strokeWidth="4"
            />
            {points.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r="8" fill="white" />
            ))}
          </svg>
          <div className="absolute left-3 top-3 rounded bg-black/70 px-2 py-1 text-[10px] text-slate-400">
            Click to draw zone · {points.length} points
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          />
          <button
            onClick={save}
            disabled={points.length < 3 || saving}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm disabled:opacity-40"
          >
            {saving ? 'Saving…' : 'Save zone'}
          </button>
          <button onClick={() => setPoints([])} className="rounded-lg border border-slate-700 px-4 py-2 text-sm">
            Clear
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
        <div className="mt-4 space-y-2">
          {zones.map((z) => (
            <div key={z.id} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs">
              <span>
                <b className="text-slate-200">{z.name}</b>
                <span className="ml-2 text-slate-500">
                  {z.points.length} points · {z.trigger_object} entry
                </span>
              </span>
              <button
                onClick={async () => {
                  await deleteZone(cameraId, z.id)
                  setZones((zs) => zs.filter((x) => x.id !== z.id))
                }}
                className="text-red-400"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
