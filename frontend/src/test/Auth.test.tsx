import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginPage } from '../pages/LoginPage'
import { RegisterPage } from '../pages/RegisterPage'
import { ForgotPasswordPage } from '../pages/ForgotPasswordPage'
import { ResetPasswordPage } from '../pages/ResetPasswordPage'
import { VerifyEmailPage } from '../pages/VerifyEmailPage'
import { renderWithProviders } from './utils'
import * as authService from '../services/auth'

const mockLogin = vi.fn()
const mockRegister = vi.fn()

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    status: 'anonymous',
    login: mockLogin,
    register: mockRegister,
    user: null,
  }),
}))

vi.mock('../services/auth', () => ({
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  verifyEmail: vi.fn(),
  resendVerification: vi.fn(),
}))

describe('Authentication Pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('LoginPage', () => {
    it('renders login form elements with accessible inputs', () => {
      renderWithProviders(<LoginPage />)
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Sign in$/i })).toBeInTheDocument()
      expect(screen.getByText(/Forgot password\?/i)).toBeInTheDocument()
    })

    it('submits valid credentials and triggers login action', async () => {
      mockLogin.mockResolvedValueOnce(undefined)
      renderWithProviders(<LoginPage />)

      fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'user@example.com' } })
      fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'SecurePass123!' } })
      fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }))

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith('user@example.com', 'SecurePass123!')
      })
    })

    it('displays error message when login fails', async () => {
      mockLogin.mockRejectedValueOnce(new Error('Invalid email or password'))
      renderWithProviders(<LoginPage />)

      fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'user@example.com' } })
      fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'WrongPass!' } })
      fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }))

      await waitFor(() => {
        expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument()
      })
    })
  })

  describe('RegisterPage', () => {
    it('renders registration form fields', () => {
      renderWithProviders(<RegisterPage />)
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/^Password$/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Confirm password/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument()
    })

    it('submits registration successfully when passwords match', async () => {
      mockRegister.mockResolvedValueOnce(undefined)
      renderWithProviders(<RegisterPage />)

      fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'newuser@example.com' } })
      fireEvent.change(screen.getByLabelText(/^Password$/i), { target: { value: 'ValidPass123!AndLong' } })
      fireEvent.change(screen.getByLabelText(/Confirm password/i), { target: { value: 'ValidPass123!AndLong' } })
      fireEvent.click(screen.getByRole('button', { name: /create account/i }))

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith('newuser@example.com', 'ValidPass123!AndLong', undefined)
        expect(screen.getByText(/Check your email/i)).toBeInTheDocument()
      })
    })
  })

  describe('ForgotPasswordPage', () => {
    it('renders email input and triggers forgotPassword service call', async () => {
      vi.mocked(authService.forgotPassword).mockResolvedValueOnce({
        message: 'If an account exists, a reset link has been sent.',
      })
      renderWithProviders(<ForgotPasswordPage />)

      const emailInput = screen.getByLabelText(/Email/i)
      fireEvent.change(emailInput, { target: { value: 'recover@example.com' } })
      fireEvent.click(screen.getByRole('button', { name: /send password reset link/i }))

      await waitFor(() => {
        expect(authService.forgotPassword).toHaveBeenCalledWith('recover@example.com')
        expect(screen.getByText(/Check your email/i)).toBeInTheDocument()
      })
    })
  })

  describe('ResetPasswordPage', () => {
    it('shows missing token error if no token is provided in query params', () => {
      renderWithProviders(<ResetPasswordPage />, { route: '/reset-password' })
      expect(screen.getByText(/No reset token was found in the link/i)).toBeInTheDocument()
    })

    it('submits new password when token is present', async () => {
      vi.mocked(authService.resetPassword).mockResolvedValueOnce({
        message: 'Password reset successfully.',
      })
      renderWithProviders(<ResetPasswordPage />, { route: '/reset-password?token=valid-reset-token' })

      const newPassInput = screen.getByLabelText(/^New password$/i)
      const confirmPassInput = screen.getByLabelText(/Confirm new password/i)

      fireEvent.change(newPassInput, { target: { value: 'BrandNewPassword123!' } })
      fireEvent.change(confirmPassInput, { target: { value: 'BrandNewPassword123!' } })
      fireEvent.click(screen.getByRole('button', { name: /update password/i }))

      await waitFor(() => {
        expect(authService.resetPassword).toHaveBeenCalledWith('valid-reset-token', 'BrandNewPassword123!')
        expect(screen.getByText(/Password updated/i)).toBeInTheDocument()
      })
    })
  })

  describe('VerifyEmailPage', () => {
    it('shows no token message when query param is absent', () => {
      renderWithProviders(<VerifyEmailPage />, { route: '/verify-email' })
      expect(screen.getByText(/Missing verification link/i)).toBeInTheDocument()
    })

    it('calls verifyEmail when token is provided', async () => {
      vi.mocked(authService.verifyEmail).mockResolvedValueOnce({
        message: 'Email verified successfully.',
      })
      renderWithProviders(<VerifyEmailPage />, { route: '/verify-email?token=valid-verify-token' })

      await waitFor(() => {
        expect(authService.verifyEmail).toHaveBeenCalledWith('valid-verify-token')
        expect(screen.getByText(/Email verified/i)).toBeInTheDocument()
      })
    })
  })
})
