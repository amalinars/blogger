import { getAllPosts, getCategories, getAllTags, getArchive } from '@/lib/db';
import { HomeFeed } from '@/components/HomeFeed';


export default async function HomePage() {
  const posts = getAllPosts({ status: 'published' });
  const categories = getCategories();
  const tags = getAllTags();
  const archives = getArchive();

  return (
    <div className="animate-fadeIn">
      <HomeFeed
        initialPosts={posts}
        categories={categories}
        tags={tags}
        archives={archives}
      />
    </div>
  );
}
