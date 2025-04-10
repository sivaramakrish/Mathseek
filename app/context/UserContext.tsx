import React, { createContext, useState } from 'react';

type User = {
  name: string;
  email: string;
  avatar?: string;
  plan: string;
  tokens: number;
  dailyUsage: number;
  monthlyUsage: number;
  dailyLimit: number;
  monthlyLimit: number;
  resetIn: string;
};

type UserContextType = {
  user: User;
  updateUser: (updatedUser: User) => void;
};

export const UserContext = createContext<UserContextType>({
  user: {
    name: 'John Doe',
    email: 'john@example.com',
    plan: 'Premium',
    tokens: 25000,
    dailyUsage: 5840,
    monthlyUsage: 120000,
    dailyLimit: 10000,
    monthlyLimit: 300000,
    resetIn: '6h 42m'
  },
  updateUser: () => {},
});

export const UserProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  const [user, setUser] = useState<User>({
    name: 'John Doe',
    email: 'john@example.com',
    plan: 'Premium',
    tokens: 25000,
    dailyUsage: 5840,
    monthlyUsage: 120000,
    dailyLimit: 10000,
    monthlyLimit: 300000,
    resetIn: '6h 42m'
  });

  return (
    <UserContext.Provider value={{ user, updateUser: setUser }}>
      {children}
    </UserContext.Provider>
  );
};
