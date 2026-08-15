import { render, screen } from '@testing-library/react'
import { vi, describe, expect, test } from 'vitest'
import AnswerPanel from '../components/deepdive/AnswerPanel'

vi.mock('../store', () => ({
  useStore: () => ({ settings: { simplified: true } }),
}))

vi.mock('../components/charts', () => ({
  HistoryChart: () => null,
}))

const company = {
  company: 'DemoBank SG', ticker: 'SGX:DEMO', sector: 'Financials — Banks', _origin: 'sample',
  layer_a: { esg_score_static: '22.4 (Medium Risk)', as_of_date: '2023-09-30' },
  layer_b: { momentum: {}, digital_ai_signal: {}, conflicting_signals: {} },
} as any

const answer = {
  question_to_ask: 'Is the AI gap a near-term risk?',
  what_rating_sees: 'Medium Risk, as of 2023.',
  what_we_see: 'AI governance hiring is accelerating.',
  check_before_monday: 'Check the next disclosure.',
  competes_summary: 'The rating is stale versus the live governance gap.',
  reasoning: ['The baseline is stale.'], sources: [],
} as any

describe('AnswerPanel', () => {
  test('renders the Contract C verdict and four supporting lines', () => {
    render(<AnswerPanel answer={answer} company={company} narrowed={null} />)
    expect(screen.getByText(answer.competes_summary)).toBeInTheDocument()
    expect(screen.getByText(answer.what_rating_sees)).toBeInTheDocument()
    expect(screen.getByText(answer.what_we_see)).toBeInTheDocument()
    expect(screen.getByText(answer.check_before_monday)).toBeInTheDocument()
  })
})
