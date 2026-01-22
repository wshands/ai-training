import React from 'react';
import { SignIn } from '@clerk/clerk-react';

const Login = () => {
  return (
    <div className="max-w-md mx-auto">
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
        afterSignInUrl="/"
        afterSignUpUrl="/"
      />
    </div>
  );
};

export default Login;
