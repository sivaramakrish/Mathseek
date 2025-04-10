import { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import RootNavigator from './app/navigation/RootNavigator';
import { UserProvider } from './app/context/UserContext';
import * as SecureStore from 'expo-secure-store';

export default function App() {

  const generateAnonymousToken = async () => {
    try {
      const existingToken = await SecureStore.getItemAsync('anonymousToken');
      if (!existingToken) {
        const response = await fetch('http://localhost:8000/api/anonymous/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const contentType = response.headers.get('content-type');
        if (!contentType?.includes('application/json')) {
          throw new Error('Invalid response format');
        }

        const tokenData = await response.json();
        if (!tokenData?.token) {
          throw new Error('Invalid token received');
        }
        
        await SecureStore.setItemAsync('anonymousToken', tokenData.token);
      }
    } catch (error) {
      console.error('Token generation failed:', error);
    };
  };

  useEffect(() => {
    generateAnonymousToken();
  }, []);

  return (
    <UserProvider>
      <NavigationContainer>
        <RootNavigator />
      </NavigationContainer>
    </UserProvider>
  );
}
