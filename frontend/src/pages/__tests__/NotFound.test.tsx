import { describe, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { NotFound } from '../NotFound'

describe('NotFound', () => {
  it('renders the 404 message and navigation links', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    )

    expect(screen.getByText(/error 404/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /back to home/i })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: /my interviews/i })).toHaveAttribute('href', '/my-interviews')
    expect(screen.getByRole('link', { name: /aura home/i })).toHaveAttribute('href', '/')
  })
})
