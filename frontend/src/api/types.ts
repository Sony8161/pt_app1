// Shapes of the API responses (camelCase after conversion). Money fields are null for employees.

export type Role = 'admin' | 'manager' | 'employee'
export type RiskLevel = 'done' | 'on_track' | 'at_risk' | 'overdue'
export type ProjectStatus = 'planned' | 'active' | 'completed' | 'archived'
export type MilestoneStatus = 'pending' | 'in_progress' | 'completed'

export interface User {
  id: string
  username: string
  name: string
  email: string
  jobTitle: string
  role: Role
  managerId: string | null
  mustChangePassword: boolean
  archivedAt: string | null
  salary: number | null
}

export interface UserList { items: User[]; total: number }
export interface UserCreated { user: User; temporaryPassword: string }
export interface PasswordReset { temporaryPassword: string }
export interface TokenResponse { accessToken: string; expiresAt: number; user: User }

export interface ProjectSummary {
  daysTotal: number
  daysElapsed: number
  daysRemaining: number
  schedulePct: number
  hoursWorked: number
  hoursRemaining: number
  hoursPct: number | null
  milestonesTotal: number
  milestonesDone: number
  milestonesOverdue: number
  milestonesPct: number | null
  teamSize: number
  riskLevel: RiskLevel
  riskReasons: string[]
  laborCost: number | null
  forecastCost: number | null
  otherCost: number | null
  totalCost: number | null
  budgetRemaining: number | null
  budgetPct: number | null
}

export interface Project {
  id: string
  name: string
  description: string
  manager: { id: string; name: string }
  status: ProjectStatus
  startDate: string
  endDate: string
  allocatedHours: number
  budgetAmount: number | null
  completedAt: string | null
  archivedAt: string | null
  summary: ProjectSummary
}

export interface ProjectList { items: Project[]; total: number; page: number; pageSize: number }

export interface Milestone {
  id: string
  projectId: string
  name: string
  description: string
  startDate: string
  dueDate: string
  status: MilestoneStatus
  isOverdue: boolean
  allocatedHours: number
  hoursWorked: number
  budgetAmount: number | null
  laborCost: number | null
  budgetPct: number | null
  assignees: number
  deliverablesTotal: number
  deliverablesDone: number
  completedAt: string | null
  reviewNote: string
  archivedAt: string | null
}

export interface MilestoneList { items: Milestone[]; total: number; plannedHours: number; plannedBudget: number | null }

export interface Deliverable {
  id: string
  milestoneId: string
  name: string
  description: string
  done: boolean
  doneAt: string | null
}

export interface DeliverableList { items: Deliverable[]; total: number; done: number; readyToComplete: boolean }

export interface Assignee {
  assignmentId: string
  userId: string
  name: string
  jobTitle: string
  milestoneId: string
  milestoneName: string
  startDate: string
  endDate: string
  daysWorked: number
  hoursWorked: number
  laborCost: number | null
}

export interface AssigneeList { items: Assignee[]; total: number; hoursWorked: number; laborCost: number | null }

export type CostCategory = 'technology' | 'license' | 'vendor' | 'travel' | 'other'

export interface Cost {
  id: string
  category: CostCategory
  description: string
  amount: number
  incurredOn: string
}

export interface CostList {
  items: Cost[]
  total: number
  otherCost: number
  laborCost: number
  totalCost: number
  budgetAmount: number
  budgetRemaining: number
}

export interface WorkRef {
  projectId: string
  projectName: string
  milestoneId: string
  milestoneName: string
  startDate: string
  endDate: string
}

export interface PersonAllocation {
  userId: string
  name: string
  jobTitle: string
  managerName: string | null
  state: 'allocated' | 'available'
  currentWork: WorkRef | null
  nextWork: WorkRef | null
  hoursThisWeek: number
  weekCapacity: number
}

export interface Overview {
  asOf: string
  counts: { projects: number; planned: number; active: number; completed: number; onTrack: number; atRisk: number; overdue: number }
  totals: { budget: number; spent: number; laborCost: number; otherCost: number; budgetRemaining: number; forecastCost: number; hoursAllocated: number; hoursWorked: number }
  projects: Project[]
  allocation: PersonAllocation[]
  availablePeople: number
}

export interface MyMilestone {
  projectId: string
  projectName: string
  milestoneId: string
  milestoneName: string
  status: string
  startDate: string
  endDate: string
  dueDate: string
  deliverablesTotal: number
  deliverablesDone: number
}

export interface MyDashboard {
  asOf: string
  currentWork: WorkRef | null
  myMilestones: MyMilestone[]
  projects: Project[]
  hoursToday: number
  hoursThisWeek: number
  weekCapacity: number
}

export interface DemoSeedResult {
  created: boolean
  message: string
  accounts: { name: string; role: Role; username: string; temporaryPassword: string }[]
}
