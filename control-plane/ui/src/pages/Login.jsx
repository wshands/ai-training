import React from 'react';
import { SignIn } from '@clerk/clerk-react';

const clerkAppearance = {
  variables: {
    colorPrimary: '#0f172a',
    colorText: '#0f172a',
    colorTextSecondary: '#475569',
    colorBackground: '#ffffff',
    colorInputBackground: '#ffffff',
    colorInputText: '#0f172a',
    colorShadows: 'rgba(15, 23, 42, 0.08)',
    borderRadius: '12px',
    fontFamily: 'Space Grotesk, system-ui, sans-serif',
  },
  elements: {
    rootBox: 'bg-transparent',
    card: 'shadow-none border border-slate-200 rounded-xl',
    headerTitle: 'text-slate-900',
    headerSubtitle: 'text-slate-500',
    formButtonPrimary: 'bg-slate-900 hover:bg-slate-800 text-white',
    formButtonReset: 'text-slate-700 hover:text-slate-900',
    formFieldLabel: 'text-slate-700',
    formFieldInput: 'border-slate-300 focus:border-slate-400',
    footer: 'hidden',
    footerAction: 'hidden',
    footerActionText: 'hidden',
    footerActionLink: 'hidden',
  },
};

const Login = () => {
  return (
    <div className="max-w-md mx-auto">
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
        afterSignInUrl="/"
        afterSignUpUrl="/"
        appearance={clerkAppearance}
      />
    </div>
  );
};

export default Login;
