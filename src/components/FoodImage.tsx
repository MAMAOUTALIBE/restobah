export function FoodImage({image,alt='',className=''}:{image:string;alt?:string;className?:string}){
  if(image.startsWith('stc-category-'))return <span role={alt?'img':undefined} aria-label={alt||undefined} aria-hidden={!alt||undefined} className={`food-image category-packshot category-packshot-${image.slice(-1)} ${className}`}/>;
  const source=/^(https?:\/\/|\/)/.test(image)?image:`/images/${image}.jpg`;
  return <img className={`food-image ${className}`} src={source} alt={alt} loading="lazy" onError={event=>{const fallback='/images/burger.jpg';if(!event.currentTarget.src.endsWith(fallback))event.currentTarget.src=fallback;}}/>;
}
