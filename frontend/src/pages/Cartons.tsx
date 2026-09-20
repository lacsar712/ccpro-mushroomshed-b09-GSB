import { For, Show, createMemo, createSignal, onMount } from 'solid-js'
import { useParams } from '@solidjs/router'
import { api } from '../api/client'
import type { Carton, FlushHarvest, ReconcileResponse, Room, Shed } from '../types'

export default function Cartons() {
  const params = useParams<{ shedId: string }>()
  const shedId = createMemo(() => Number(params.shedId))

  const [shed, setShed] = createSignal<Shed | null>(null)
  const [cartons, setCartons] = createSignal<Carton[]>([])
  const [rooms, setRooms] = createSignal<Room[]>([])
  const [harvests, setHarvests] = createSignal<FlushHarvest[]>([])
  const [reconcile, setReconcile] = createSignal<ReconcileResponse | null>(null)
  const [role, setRole] = createSignal('')
  const [cartonNo, setCartonNo] = createSignal('')
  // 每只箱选中的待加入潮次：cartonId -> harvestId
  const [picked, setPicked] = createSignal<Record<number, string>>({})
  const [error, setError] = createSignal('')
  const [busy, setBusy] = createSignal(false)

  const roomCode = (roomId: number) => rooms().find((r) => r.id === roomId)?.roomCode ?? `#${roomId}`

  // 该棚下尚未进入任何箱子的潮次，才能直接加入未封箱
  const availableHarvests = createMemo<FlushHarvest[]>(() => {
    const roomIds = new Set(rooms().map((r) => r.id))
    const boxed = new Set<number>()
    for (const c of cartons()) for (const it of c.items) boxed.add(it.harvestId)
    return harvests().filter((h) => roomIds.has(h.roomId) && !boxed.has(h.id))
  })

  async function load() {
    setError('')
    try {
      const [shedList, cartonList, roomList, harvestList, rec, me] = await Promise.all([
        api<Shed[]>('/api/sheds'),
        api<Carton[]>(`/api/cartons?shedId=${shedId()}`),
        api<Room[]>(`/api/rooms?shedId=${shedId()}`),
        api<FlushHarvest[]>('/api/flush-harvests'),
        api<ReconcileResponse>('/api/cartons/reconcile'),
        api<{ role: string }>('/api/auth/me'),
      ])
      setShed(shedList.find((s) => s.id === shedId()) ?? null)
      setCartons(cartonList)
      setRooms(roomList)
      setHarvests(harvestList)
      setReconcile(rec)
      setRole(me.role)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    }
  }

  onMount(load)

  async function run(fn: () => Promise<unknown>, ok?: () => void) {
    setError('')
    setBusy(true)
    try {
      await fn()
      ok?.()
      await load()
    } catch (err) {
      // 失败原文展示，不做吞改
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  async function createCarton(e: Event) {
    e.preventDefault()
    const no = cartonNo().trim()
    if (!no) return
    await run(() =>
      api('/api/cartons', { method: 'POST', body: JSON.stringify({ cartonNo: no, shedId: shedId() }) })
    )
    setCartonNo('')
  }

  function pick(c: Carton) {
    return picked()[c.id] ?? ''
  }

  function setPick(cartonId: number, value: string) {
    setPicked({ ...picked(), [cartonId]: value })
  }

  return (
    <div>
      <header class="page-header">
        <h1>拼箱 · {shed()?.name ?? `菇房 #${shedId()}`}</h1>
        <p class="muted">
          多笔潮次收进一只纸箱；箱号在同一菇房下唯一，不同菇房撞号不串棚。封箱后不能再加入或移出；
          <strong>至少两笔潮次且重量合计大于 0 才可封箱</strong>。拆封仅管理员。
        </p>
      </header>

      <Show when={error()}>
        <div class="error">{error()}</div>
      </Show>

      <Show when={reconcile()}>
        <section class="panel" style={{ margin: '16px 0' }}>
          <h2 style={{ margin: '0 0 10px', 'font-size': '16px' }}>对账汇总（byShed）</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>菇房</th>
                  <th>箱数</th>
                  <th>公斤合计</th>
                </tr>
              </thead>
              <tbody>
                <For each={reconcile()!.byShed}>
                  {(r) => (
                    <tr style={r.shedId === shedId() ? { 'font-weight': '700' } : undefined}>
                      <td>{r.shedName}</td>
                      <td>{r.cartonCount}</td>
                      <td>{r.totalKg}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </div>
        </section>
      </Show>

      <form class="panel form-grid" onSubmit={createCarton}>
        <label>
          新箱号（本菇房内唯一）
          <input
            value={cartonNo()}
            onInput={(e) => setCartonNo(e.currentTarget.value)}
            required
          />
        </label>
        <button type="submit" class="btn primary" disabled={busy()} style={{ 'align-self': 'end' }}>
          新建未封箱
        </button>
      </form>

      <div style={{ display: 'grid', gap: '16px', 'margin-top': '16px' }}>
        <For each={cartons()}>
          {(c) => (
            <section class="panel">
              <div
                style={{
                  display: 'flex',
                  'align-items': 'center',
                  gap: '12px',
                  'justify-content': 'space-between',
                }}
              >
                <div>
                  <h2 style={{ margin: 0, 'font-size': '17px' }}>
                    箱号 {c.cartonNo} <span class="muted">#{c.id}</span>
                  </h2>
                  <div style={{ 'margin-top': '6px' }}>
                    <Show
                      when={c.sealedAt}
                      fallback={<span class="badge fruiting">未封箱</span>}
                    >
                      <span class="badge sanitize">已封箱 {new Date(c.sealedAt!).toLocaleString()}</span>
                    </Show>
                    <span style={{ 'margin-left': '10px' }}>
                      合计 <strong>{c.totalKg}</strong> kg · {c.items.length} 笔
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Show when={!c.sealedAt}>
                    <button
                      type="button"
                      class="btn primary"
                      disabled={busy()}
                      onClick={() => run(() => api(`/api/cartons/${c.id}/seal`, { method: 'POST' }))}
                    >
                      封箱
                    </button>
                  </Show>
                  <Show when={c.sealedAt && role() === 'admin'}>
                    <button
                      type="button"
                      class="btn ghost"
                      disabled={busy()}
                      onClick={() =>
                        run(() => api(`/api/cartons/${c.id}/unseal`, { method: 'POST' }))
                      }
                    >
                      管理员拆封
                    </button>
                  </Show>
                </div>
              </div>

              <div class="table-wrap" style={{ 'margin-top': '12px' }}>
                <table>
                  <thead>
                    <tr>
                      <th>条目</th>
                      <th>潮次</th>
                      <th>出菇室</th>
                      <th>采收时间</th>
                      <th>潮次号</th>
                      <th>重量</th>
                      <th>等级</th>
                      <th>操作人</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    <For each={c.items}>
                      {(it) => (
                        <tr>
                          <td>{it.id}</td>
                          <td>#{it.harvestId}</td>
                          <td>{roomCode(it.roomId)}</td>
                          <td>{new Date(it.harvestedAt).toLocaleString()}</td>
                          <td>{it.flushNo}</td>
                          <td>{it.weightKg}</td>
                          <td>
                            <span class={`badge grade-${it.grade.toLowerCase()}`}>{it.grade}</span>
                          </td>
                          <td>{it.operatorName}</td>
                          <td>
                            <Show when={!c.sealedAt}>
                              <button
                                type="button"
                                class="btn ghost"
                                disabled={busy()}
                                onClick={() =>
                                  run(() =>
                                    api(`/api/cartons/${c.id}/items/${it.id}`, {
                                      method: 'DELETE',
                                    })
                                  )
                                }
                              >
                                移出
                              </button>
                            </Show>
                          </td>
                        </tr>
                      )}
                    </For>
                  </tbody>
                </table>
              </div>

              <Show when={!c.sealedAt}>
                <form
                  class="form-grid"
                  style={{ 'margin-top': '12px' }}
                  onSubmit={(e) => {
                    e.preventDefault()
                    const harvestId = Number(pick(c))
                    if (!harvestId) return
                    setPick(c.id, '')
                    run(() =>
                      api(`/api/cartons/${c.id}/items`, {
                        method: 'POST',
                        body: JSON.stringify({ harvestId }),
                      })
                    )
                  }}
                >
                  <label>
                    加入本棚潮次
                    <select value={pick(c)} onChange={(e) => setPick(c.id, e.currentTarget.value)}>
                      <option value="">选择尚未拼箱的潮次</option>
                      <For each={availableHarvests()}>
                        {(h) => (
                          <option value={String(h.id)}>
                            #{h.id} · {roomCode(h.roomId)} · 第{h.flushNo}潮 · {h.weightKg}kg · {h.grade}
                          </option>
                        )}
                      </For>
                    </select>
                  </label>
                  <button type="submit" class="btn ghost" disabled={busy()} style={{ 'align-self': 'end' }}>
                    加入
                  </button>
                </form>
              </Show>
            </section>
          )}
        </For>
      </div>
    </div>
  )
}
