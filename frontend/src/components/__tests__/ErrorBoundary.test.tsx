import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ErrorBoundary from '../ErrorBoundary'

function ProblemChild(): React.ReactElement {
  throw new Error('boom')
}

function makeThrower(message: string) {
  return function Throwing(): React.ReactElement {
    throw new Error(message)
  }
}

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <p>All good</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('renders default fallback UI when a child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <ProblemChild />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument()

    vi.restoreAllMocks()
  })

  it('renders custom fallback when provided', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary fallback={<div>Custom error view</div>}>
        <ProblemChild />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Custom error view')).toBeInTheDocument()

    vi.restoreAllMocks()
  })

  /**
   * A deploy landing under an open tab leaves it pointing at chunk files
   * Vercel no longer serves. The recovery is a reload — and the stylesheet
   * spelling of that failure was not recognised until 2026-09-09, so a
   * teacher mid-deploy on 2026-09-06 got the error screen instead.
   */
  describe('stale-chunk auto-recovery', () => {
    const reload = vi.fn()

    beforeEach(() => {
      sessionStorage.clear()
      vi.stubGlobal('location', { reload })
      vi.spyOn(console, 'error').mockImplementation(() => {})
      reload.mockClear()
    })

    afterEach(() => {
      vi.unstubAllGlobals()
      vi.restoreAllMocks()
    })

    it.each([
      ['script', 'Failed to fetch dynamically imported module: /assets/Ch-1.js'],
      ['stylesheet', 'Unable to preload CSS for https://equipbible.com/assets/katex-Ddr6Z9Sf.css'],
    ])('reloads once when a lazy %s is gone', (_label, message) => {
      const Throwing = makeThrower(message)
      render(
        <ErrorBoundary>
          <Throwing />
        </ErrorBoundary>,
      )
      expect(reload).toHaveBeenCalledOnce()
    })

    it('leaves an ordinary bug to the error screen', () => {
      const Throwing = makeThrower("Cannot read properties of undefined (reading 'map')")
      render(
        <ErrorBoundary>
          <Throwing />
        </ErrorBoundary>,
      )
      expect(reload).not.toHaveBeenCalled()
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })
  })
})
