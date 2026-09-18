import { copyVariantA } from './variant-a';
import { copyVariantB } from './variant-b';

export const copyVariants = {
  a: copyVariantA,
  b: copyVariantB,
};

// Default active variant (change to 'b' for DDB minimalist variant)
export const activeCopy = copyVariantA;

export default activeCopy;
