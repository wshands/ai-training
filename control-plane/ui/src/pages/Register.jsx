import React from 'react';
import { SignUp } from '@clerk/clerk-react';

const Register = () => {
  return (
    <div className="max-w-md mx-auto">
      <SignUp
        routing="path"
        path="/register"
        signInUrl="/login"
        afterSignInUrl="/"
        afterSignUpUrl="/"
      />
    </div>
  );
};

export default Register;
