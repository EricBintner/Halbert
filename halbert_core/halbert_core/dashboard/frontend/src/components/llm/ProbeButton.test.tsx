// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ProbeButton against the /compute/endpoint-probe route.
 *
 * The component shipped before the route did, so every click rendered
 * "Probe failed". These pin the request it sends and the two response
 * envelopes the backend can return.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ProbeButton, type ProbeResult } from './ProbeButton'

const RESULT: ProbeResult = {
  endpoint_id: 'ep-1',
  probed_at: 1_700_000_000,
  burst_size: 20,
  wall_clock_ms: { p50: 120, p90: 260, p99: 1400 },
  saturation_point: 8,
  saturation_method: 'latency_staircase',
  recommended_concurrent: 4,
  successes: 20,
  errors: 0,
  histogram_path: null,
}

function mockFetch(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('ProbeButton', () => {
  it('posts endpoint_id and burst_size to the probe route', async () => {
    const fetchMock = mockFetch({ data: RESULT })
    render(<ProbeButton endpointId="ep-1" burstSize={20} />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/compute/endpoint-probe')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ endpoint_id: 'ep-1', burst_size: 20 })
  })

  it('renders the latency percentiles and the saturation point', async () => {
    mockFetch({ data: RESULT })
    render(<ProbeButton endpointId="ep-1" />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    expect(await screen.findByText(/20\/20 ok/)).toBeInTheDocument()
    expect(screen.getByText('120ms')).toBeInTheDocument()
    expect(screen.getByText('1.4s')).toBeInTheDocument()
    expect(screen.getByText('8 concurrent')).toBeInTheDocument()
  })

  it('hands the recommendation to onApply', async () => {
    mockFetch({ data: RESULT })
    const onApply = vi.fn()
    render(<ProbeButton endpointId="ep-1" onApply={onApply} />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))
    await userEvent.click(await screen.findByRole('button', { name: /apply 4 to plan/i }))

    expect(onApply).toHaveBeenCalledWith(4)
  })

  it('says so when nothing saturated instead of inventing a cap', async () => {
    mockFetch({
      data: { ...RESULT, saturation_point: null, saturation_method: 'none', recommended_concurrent: null },
    })
    render(<ProbeButton endpointId="ep-1" />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    expect(await screen.findByText(/no saturation detected/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument()
  })

  it('surfaces the backend error message', async () => {
    mockFetch({ error: { message: "No saved endpoint with id 'ep-1'" } }, false)
    render(<ProbeButton endpointId="ep-1" />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("No saved endpoint with id 'ep-1'")
  })

  it('reports a network failure rather than hanging in "probing"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const onProbeComplete = vi.fn()
    render(<ProbeButton endpointId="ep-1" onProbeComplete={onProbeComplete} />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('offline')
    expect(onProbeComplete).toHaveBeenCalledWith(null, 'offline')
  })

  it('disables the button while a probe is in flight', async () => {
    // Deliberately never settles: the point is the state *during* the probe,
    // and resolving after the assertion only produces an act() warning.
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<ProbeButton endpointId="ep-1" />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    expect(screen.getByRole('button', { name: /probing/i })).toBeDisabled()
  })

  it('accepts a bare result body as well as a {data} envelope', async () => {
    mockFetch(RESULT)
    render(<ProbeButton endpointId="ep-1" />)

    await userEvent.click(screen.getByRole('button', { name: /probe capacity/i }))

    expect(await screen.findByText(/20\/20 ok/)).toBeInTheDocument()
  })
})
