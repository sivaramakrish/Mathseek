import { NavigationContainer } from '@react-navigation/native'; // Exactly thisw
import RootNavigator from './app/navigation/RootNavigator';
import { UserProvider } from './app/context/UserContext';

export default function App() {
  return (
    <UserProvider>
      <NavigationContainer>
        <RootNavigator />
      </NavigationContainer>
    </UserProvider>
  );
}
