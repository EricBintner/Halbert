// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OnScreenKeyboard } from './OnScreenKeyboard'

describe('OnScreenKeyboard', () => {
  it('renders the 48px mark emblem and keyboard', () => {
    render(<OnScreenKeyboard onSend={vi.fn()} onDismiss={vi.fn()} />)
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByLabelText('Message text input')).toBeTruthy()
  })

  it('quick chip click calls onSend with the chip text', () => {
    const onSend = vi.fn()
    render(<OnScreenKeyboard onSend={onSend} onDismiss={vi.fn()} />)

    fireEvent.click(screen.getByText('System Vitals'))
    expect(onSend).toHaveBeenCalledWith('System Vitals')

    fireEvent.click(screen.getByText('Check Storage'))
    expect(onSend).toHaveBeenCalledWith('Check Storage')

    fireEvent.click(screen.getByText('Lock Doors'))
    expect(onSend).toHaveBeenCalledWith('Lock Doors')

    fireEvent.click(screen.getByText('Run Health Scan'))
    expect(onSend).toHaveBeenCalledWith('Run Health Scan')
  })

  it('typing keys and pressing send calls onSend with composed text', () => {
    const onSend = vi.fn()
    render(<OnScreenKeyboard onSend={onSend} onDismiss={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Key h'))
    fireEvent.click(screen.getByLabelText('Key i'))
    fireEvent.click(screen.getByLabelText('Send message'))

    expect(onSend).toHaveBeenCalledWith('hi')
  })

  it('backspace removes the last character', () => {
    const onSend = vi.fn()
    render(<OnScreenKeyboard onSend={onSend} onDismiss={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('Key a'))
    fireEvent.click(screen.getByLabelText('Key b'))
    fireEvent.click(screen.getByLabelText('Key c'))
    fireEvent.click(screen.getByLabelText('Backspace'))

    const input = screen.getByLabelText('Message text input') as HTMLInputElement
    expect(input.value).toBe('ab')
  })

  it('send is disabled when text is empty', () => {
    render(<OnScreenKeyboard onSend={vi.fn()} onDismiss={vi.fn()} />)
    const sendBtn = screen.getByLabelText('Send message')
    expect(sendBtn).toBeDisabled()
  })

  it('dismiss button calls onDismiss', () => {
    const onDismiss = vi.fn()
    render(<OnScreenKeyboard onSend={vi.fn()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss keyboard'))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('mic button calls onMic when provided', () => {
    const onMic = vi.fn()
    render(<OnScreenKeyboard onSend={vi.fn()} onDismiss={vi.fn()} onMic={onMic} />)
    fireEvent.click(screen.getByLabelText('Switch to voice input'))
    expect(onMic).toHaveBeenCalledOnce()
  })

  it('Enter key sends the message', () => {
    const onSend = vi.fn()
    render(<OnScreenKeyboard onSend={onSend} onDismiss={vi.fn()} />)

    const input = screen.getByLabelText('Message text input')
    fireEvent.change(input, { target: { value: 'hello' } })
    fireEvent.keyDown(input, { key: 'Enter', preventDefault: () => {} } as any)

    expect(onSend).toHaveBeenCalledWith('hello')
  })

  it('space bar adds a space', () => {
    render(<OnScreenKeyboard onSend={vi.fn()} onDismiss={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Key a'))
    fireEvent.click(screen.getByLabelText('Space'))
    fireEvent.click(screen.getByLabelText('Key b'))
    const input = screen.getByLabelText('Message text input') as HTMLInputElement
    expect(input.value).toBe('a b')
  })
})
