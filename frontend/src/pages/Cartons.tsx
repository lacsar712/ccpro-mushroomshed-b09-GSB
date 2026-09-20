import { A, useParams } from '@solidjs/router'
import { createSignal, For, onMount, Show } from 'solid-js'
import { api } from '../api/client'
import type { Carton, FlushHarvest, Reconcile, Room, Shed } from '../types'

export default function Cartons() {
  const params = useParams<{ id: string }>()
  const shedId = () => Number(params.id)

  const [shed, setShed] = createSignal<Shed | null>(null)
  const [cartons, setCartons] = createSignal<Carton[]>([])
  const [harvests, setHarvests] = createSignal<FlushHarvest[]>([])
  const [reconcile, setReconcile] = createSignal<Reconcile | null>(null)
  const [isAdmin, setIsAdmin] = createSignal(false)
  const [cartonNo, setCartonNo] = createSignal('')
  const [error, setError] = createSignal('')
  const [busy, setBusy] = createSignal(false)

  // 每个未封箱一只「加入潮次」下拉
  const [picked, setPicked] = createSignal<Record<number, string>>({})
  // 每条目改挂目标箱
  const [moveTarget, setMoveTarget] = createSignal<Record<string, string>>({})

  async function load() {
    const [shedList, cartonList, allHarvests, roomList, rec, me] = await Promise.all([
      api<Shed[]>('/api/sheds'),
      api<Carton[]>(`/api/sheds/${shedId()}/cartons`),
      api<FlushHarvest[]>('/api/flush-harvests'),
      api<Room[]>('/api/rooms'),
      api<Reconcile>('/api/cartons/reconcile'),
      api<{ username: string; role: string; displayName: string }>('/api/auth/me'),
    ])
    setShed(shedList.find((s) => s.id === shedId()) ?? null)
    setCartons(cartonList)
    const roomIds = new Set(roomList.filter((r) => r.shedId === shedId()).map((r) => r.id))
    setHarvests(allHarvests.filter((h) => roomIds.has(h.roomId)))
    setReconcile(rec)
    setIsAdmin(me.role === 'admin')
  }

  onMount(() => {
    load().catch((e) => setError(e.message))
  })

  const boxedHarvestIds = () => new Set(cartons().flatMap((c) => c.items.map((i) => i.harvestId)))
  const availableHarvests = () => harvests().filter((h) => !boxedHarvestIds().has(h.id))

  function run(label: string, fn: () => Promise<void>) {
    return async () => {
      setError('')
      setBusy(true)
      try {
        await fn()
        await load()
      } catch (err) {
        // 失败原文展示
        setError(`${label}失败：${err instanceof Error ? err.message : String(err)}`)
      } finally {
        setBusy(false)
      }
    }
  }

  async function createCarton(e: Event) {
    e.preventDefault()
    setError('')
    if (!cartonNo().trim()) return
    setBusy(true)
    try {
      await api(`/api/sheds/${shedId()}/cartons`, {
        method: 'POST',
        body: JSON.stringify({ shedId: shedId(), cartonNo: cartonNo().trim() }),
      })
      setCartonNo('')
      await load()
    } catch (err) {
      setError(`建箱失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }

  // 改挂 = 先从原未封箱移出，再加入另一只未封箱
  async function moveItem(harvestId: number, fromCartonId: number) {
    const targetId = Number(moveTarget()[`${fromCartonId}:${harvestId}`])
    if (!targetId) return
    setError('')
    setBusy(true)
    try {
      await api(`/api/cartons/${fromCartonId}/items/${harvestId}`, { method: 'DELETE' })
      await api(`/api/cartons/${targetId}/items`, {
        method: 'POST',
        body: JSON.stringify({ harvestId }),
      })
      await load()
    } catch (err) {
      setError(`改挂失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }

  const shedReconcile = () => reconcile()?.byShed.find((b) => b.shedId === shedId()) ?? null

  return (
    <div>
      <header class="page-header">
        <h1>拼箱 · {shed()?.name ?? `菇房 #${shedId()}`}</h1>
        <p class="muted">
          把多笔潮次（FlushHarvest）收进同一纸箱；至少两笔潮次、重量合计大于 0 才可封箱
        </p>
        <p>
          <A class="btn ghost" href="/sheds">
            ← 返回菇房
          </A>
        </p>
      </header>
      {error() && <div class="error">{error()}</div>}

      <Show when={reconcile()}>
        <section class="panel">
          <h2>对账汇总（/api/cartons/reconcile）</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>菇房</th>
                  <th>箱数</th>
                  <th>按箱合计 kg</th>
                  <th>明细求和 kg</th>
                  <th>差额 kg</th>
                </tr>
              </thead>
              <tbody>
                <For each={reconcile()!.byShed}>
                  {(b) => (
                    <tr style={b.shedId === shedId() ? 'font-weight:700' : ''}>
                      <td>{b.shedName ?? `#${b.shedId}`}</td>
                      <td>{b.cartonCount}</td>
                      <td>{b.cartonKg}</td>
                      <td>{b.itemKg}</td>
                      <td>{b.deltaKg}</td>
                    </tr>
                  )}
                </For>
              </tbody>
              <tfoot>
                <tr>
                  <td>
                    合计{' '}
                    <span
                      class={`badge ${reconcile()!.balanced ? 'fruiting' : 'sanitize'}`}
                    >
                      {reconcile()!.balanced ? '差额 ≤ 0.001 平衡' : '不平衡'}
                    </span>
                  </td>
                  <td>{reconcile()!.totalCartons}</td>
                  <td>{reconcile()!.cartonKg}</td>
                  <td>{reconcile()!.itemKg}</td>
                  <td>{reconcile()!.deltaKg}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <Show when={shedReconcile()}>
            <p class="muted">
              本棚：{shedReconcile()!.cartonCount} 箱，按箱 {shedReconcile()!.cartonKg} kg /
              明细 {shedReconcile()!.itemKg} kg，差额 {shedReconcile()!.deltaKg} kg
            </p>
          </Show>
        </section>
      </Show>

      <form class="panel form-grid" onSubmit={createCarton}>
        <label>
          新纸箱编号（同一菇房下唯一）
          <input
            value={cartonNo()}
            onInput={(e) => setCartonNo(e.currentTarget.value)}
            placeholder="例如 C-001"
            required
          />
        </label>
        <button type="submit" class="btn primary" disabled={busy()}>
          新建未封箱
        </button>
      </form>

      <div class="carton-grid">
        <For each={cartons()}>
          {(c) => {
            const sealed = () => c.sealedAt != null
            const otherOpenCartons = () =>
              cartons().filter((o) => o.id !== c.id && o.sealedAt == null)
            return (
              <section class="panel carton-card">
                <div class="carton-head">
                  <div>
                    <strong>{c.cartonNo}</strong>{' '}
                    <span class={`badge ${sealed() ? 'sanitize' : 'fruiting'}`}>
                      {sealed() ? '已封箱' : '未封箱'}
                    </span>
                  </div>
                  <div class="muted small">
                    箱号 #{c.id}
                    <Show when={sealed()}>
                      {' '}
                      · 封箱于 {new Date(c.sealedAt!).toLocaleString()}
                    </Show>
                  </div>
                </div>

                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>潮次</th>
                        <th>室</th>
                        <th>时间</th>
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
                            <td>第 {it.flushNo} 潮</td>
                            <td>{it.roomId}</td>
                            <td>{new Date(it.harvestedAt).toLocaleString()}</td>
                            <td>{it.weightKg} kg</td>
                            <td>
                              <span class={`badge grade-${it.grade.toLowerCase()}`}>
                                {it.grade}
                              </span>
                            </td>
                            <td>{it.operatorName}</td>
                            <td>
                              <Show when={!sealed()}>
                                <button
                                  type="button"
                                  class="btn ghost"
                                  disabled={busy()}
                                  onClick={run('移出', async () => {
                                    await api(
                                      `/api/cartons/${c.id}/items/${it.harvestId}`,
                                      { method: 'DELETE' }
                                    )
                                  })}
                                >
                                  移出
                                </button>
                                <Show when={otherOpenCartons().length > 0}>
                                  <select
                                    value={moveTarget()[`${c.id}:${it.harvestId}`] ?? ''}
                                    onChange={(e) =>
                                      setMoveTarget({
                                        ...moveTarget(),
                                        [`${c.id}:${it.harvestId}`]: e.currentTarget.value,
                                      })
                                    }
                                  >
                                    <option value="">改挂到…</option>
                                    <For each={otherOpenCartons()}>
                                      {(o) => <option value={String(o.id)}>{o.cartonNo}</option>}
                                    </For>
                                  </select>
                                  <button
                                    type="button"
                                    class="btn ghost"
                                    disabled={busy()}
                                    onClick={() => moveItem(it.harvestId, c.id)}
                                  >
                                    改挂
                                  </button>
                                </Show>
                              </Show>
                            </td>
                          </tr>
                        )}
                      </For>
                    </tbody>
                  </table>
                </div>

                <p>
                  合计：<strong>{c.totalKg} kg</strong> · {c.items.length} 笔
                </p>

                <Show when={!sealed()}>
                  <div class="carton-actions">
                    <select
                      value={picked()[c.id] ?? ''}
                      onChange={(e) =>
                        setPicked({ ...picked(), [c.id]: e.currentTarget.value })
                      }
                    >
                      <option value="">选择待拼入的潮次</option>
                      <For each={availableHarvests()}>
                        {(h) => (
                          <option value={String(h.id)}>
                            #{h.id} · 室 {h.roomId} · 第{h.flushNo}潮 · {h.weightKg}kg · {h.grade}
                          </option>
                        )}
                      </For>
                    </select>
                    <button
                      type="button"
                      class="btn primary"
                      disabled={busy() || !picked()[c.id]}
                      onClick={run('加入', async () => {
                        await api(`/api/cartons/${c.id}/items`, {
                          method: 'POST',
                          body: JSON.stringify({ harvestId: Number(picked()[c.id]) }),
                        })
                      })}
                    >
                      加入潮次
                    </button>
                    <button
                      type="button"
                      class="btn ghost"
                      disabled={busy()}
                      onClick={run('封箱', async () => {
                        await api(`/api/cartons/${c.id}/seal`, { method: 'POST' })
                      })}
                    >
                      封箱
                    </button>
                  </div>
                  <Show when={c.items.length < 2}>
                    <p class="muted small">至少两笔潮次才可封箱。</p>
                  </Show>
                </Show>

                <Show when={sealed() && isAdmin()}>
                  <button
                    type="button"
                    class="btn ghost"
                    disabled={busy()}
                    onClick={run('拆封', async () => {
                      await api(`/api/cartons/${c.id}/unseal`, { method: 'POST' })
                    })}
                  >
                    拆封（仅 admin；不清空条目）
                  </button>
                </Show>
              </section>
            )
          }}
        </For>
      </div>

      <Show when={cartons().length === 0}>
        <p class="muted">本棚还没有纸箱，先在上方新建一只未封箱。</p>
      </Show>
    </div>
  )
}
