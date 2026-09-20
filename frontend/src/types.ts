export type RoomStatus = 'fruiting' | 'idle' | 'sanitize'
export type HarvestGrade = 'A' | 'B' | 'C'

export interface Shed {
  id: number
  name: string
  location: string
  notes?: string | null
}

export interface Room {
  id: number
  shedId: number
  roomCode: string
  species: string
  capacityBags: number
  status: RoomStatus
}

export interface ClimateLog {
  id: number
  roomId: number
  recordedAt: string
  tempC: number
  humidityPct: number
  co2Ppm?: number | null
  notes?: string | null
}

export interface FlushHarvest {
  id: number
  roomId: number
  harvestedAt: string
  flushNo: number
  weightKg: number
  grade: HarvestGrade
  operatorName: string
}

export interface CartonItem {
  harvestId: number
  roomId: number
  harvestedAt: string
  flushNo: number
  weightKg: number
  grade: HarvestGrade
  operatorName: string
}

export interface Carton {
  id: number
  shedId: number
  cartonNo: string
  sealedAt?: string | null
  items: CartonItem[]
  totalKg: number
}

export interface ReconcileByShed {
  shedId: number
  shedName: string | null
  cartonCount: number
  cartonKg: number
  itemKg: number
  deltaKg: number
}

export interface Reconcile {
  byShed: ReconcileByShed[]
  totalCartons: number
  cartonKg: number
  itemKg: number
  deltaKg: number
  balanced: boolean
}

export interface DashboardStats {
  shedTotal: number
  fruitingRoomCount: number
  climateLast24h: number
  harvestKgLast7d: number
}
